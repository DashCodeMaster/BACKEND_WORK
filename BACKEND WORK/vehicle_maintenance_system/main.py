import sqlite3, json, asyncio, aiohttp, heapq
from fastapi import FastAPI, UploadFile, File, Form
from datetime import date
from typing import List
from dataclasses import dataclass
app = FastAPI()
DB = "scheduler.db"
@dataclass
class Task:
    id:int; name:str; impact:float; hours:int

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.executescript('''CREATE TABLE IF NOT EXISTS depots (id INT PRIMARY KEY, hours INT);
                           CREATE TABLE IF NOT EXISTS schedules(id INTEGER PRIMARY KEY AUTOINCREMENT, depot_id INT, date TEXT, total_hours INT, total_impact REAL, output TEXT);''')

init_db()
def optimize(tasks: List[Task], max_hours : int):
    """0/1 knapsack - O(n*W) but efficient for real-world scales"""
    n = len(tasks)
    dp = [0] * (max_hours + 1)
    pick = [[] for _ in range(max_hours + 1)]
    for task in tasks:
        for w in range (max_hours, task.hours -1, -1):
            if dp[w - task.hours] + task.impact > dp[w] :
                dp[w] = dp[w - task.hours] + [task]
        best_hours = max([h for h in range(max_hours, -1, -1) if pick[h]], default=0)
        return pick[best_hours], dp[best_hours], best_hours 


async def fetch_depots():
    async with aiohttp.ClientSession() as session:
        resp = await session.get("http://20.207.123.201/evaluation-service/depots")
        if resp.status == 200:
            data = await resp.json()
            return [{"id": d["ID"], "hours" : d["MechaniHours"]} for d in data.get("depots" , [])]
        return []
    
@app.on_event("startup")
async def load_depots():
    depots = await fetch_deposits()
    with sqlite3.connect(DB) as conn:
        conn.executemany("INSERT OR REPLACE INTO depots VALUES (?, ?)" , [(d["id"], d["hours"]) for d in depots])

@app.post("/schedule")
async def schedule(depot_id: int, file: UploadFile = File(...)):
    content = await file.read()
    lines = content.decode().strip().split('\n')
    tasks = []
    for i , line in enumerate(lines[1: ], 1):
        parts = line.strip().split(',')
        if len(parts) >= 2:
            tasks.append(Task(i , f"Task_{i}", float(parts[0]), int(parts[1])))
    with sqlite3.connect(DB) as conn:
        cur = conn.execute("SELECT hours FROM depots WHERE id = ?", (depot_id))
        depot = cur.fetchone()
        if not depot:
            return  {"error":"Depot not found"}
        max_hours = depot[0]
        selected, total_impact, used_hours = optimize(tasks, max_hours)
        output = {
            "depot_id" : depot_id,
            "date" : date.today().isoformat(),
            "available_hours": max_hours,
            "used_hours" : used_hours,
            "utilization" : round(used_hours/max_hours*100, 1),
            "total_impact" : round(total_impact, 2),
            "tasks": [{"id": t.id, "name" : t.name, "impact" : t.impact, "hours" : t.hours} for t in selected],
            "backlog": len(tasks) -len(selected)
        } 
        with sqlite3.connect(DB) as conn:
            conn.execute("INSERT INTO schedules (depot_id, date, total_hours, total_impact, output) VALUES (?, ?,?,?, ?)", "ate", used_hours, total_impact, json.dumps(output))   
            conn.commit()


    import os 
    os.makedirs("vehicle_scheduling_folder/archive", exist_ok= True)
    filename = f"schedule_{depot_id}_{date.today()}.json"
    with open (f"vechicle_scheduling_folder/archive/{filename}", "w") as f:
        json.dump(output, f, indent=2)
    return output

@app.get("/outputs")
async def get_outputs():
    with sqlite3.connect(DB) as conn:
        cur = conn.execute("SELECT id, depot_id, date, total_impact, output FROM schedules ORDER BY id DESC LIMMIT 50")
        return [{"id": r[0], "depot_id": r[1], "date" :r[2], "total_impact" : r[3], "data": json.loads(r[4])} for r in cur.fetchall()]
if __name__ == "__main__":
    import unicorn 
    uvicorn.run(app, host="0.0.0.0" port = 80000)           

