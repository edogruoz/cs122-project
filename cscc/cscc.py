# CSCC Project
#
# CMSC 12200
#
# Efe Dogruoz, Ebru Ermis, Mey Abdullahoglu, Kevin Ramirez

"""
Tasks:
    write code that takes in model and use, and returns emission + spending
    write code that compares emission with average and gives rec for hours to
        cut down
    write code to rec. (alternative cars OR public transport) and gives info 
        about savings
    translate the written code to user interface
"""
import sqlite3
import subprocess
from urllib.request import urlopen

MILES_PER_HOUR = 30 #needs to be edited
SELECT_CMD = ("SELECT co2TailpipeGpm, fuelCost08,"
              " fuelCostA08, fuelType FROM vehicles ")
WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"

def get_data(url):
    response = urlopen(url)
    data = response.read()
    filename = url.split('/')[-1]
    
    with open(filename, 'wb') as csv_file:
        csv_file.write(data)

def csv_to_sql(csv_file):
    database = "cscc.db"
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute("CREATE TABLE vehicles (CO2_A REAL, CO2 REAL,"
              " fuel_cost INTEGER, fuel_cost_A INTEGER,"
              " fuel_type varchar(200), hlv INTEGER, hpv INTEGER, id INTEGER,"
              " lv2 INTEGER, lv4 INTEGER, make varchar(200),"
              " model varchar(200), pv2 INTEGER, pv4 INTEGER,"
              " v_class varchar(200), year INTEGER)")

    subprocess.call(["sqlite3", database, ".separator ','",
                     ".import trimmed.csv vehicles"])

def get_emissions(input_dict, vehicles):
    model = input_dict["model"]
    make = input_dict["make"]
    year = input_dict["year"]
    array = [model, make, year]

    if input_dict["use_miles"]:
        use = input_dict["use_miles"]
    else:
        use = input_dict["use_hours"]
        use = MILES_PER_HOUR * use
    
    s = SELECT_CMD + WHERE_CMD

    db = sqlite3.connect(vehicles)
    c = db.cursor()
    r = c.execute(s, array)
    rv = r.fetchall()
    db.close

    #to be continued

def compare_emission(data):
    pass

def get_recommendation(data):
    pass

