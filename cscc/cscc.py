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
import pandas as pd
import sqlite3
import subprocess
from urllib.request import urlopen

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

# Year bounds on dataset to reject certain user input
YEAR_LB, YEAR_UB = 1980, 2025
# Widens user search so they don't need exact year
YEAR_TOLERANCE = 5

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
    
    return filename

# POSSIBLE REPLACEMENT FOR TRIM CSV
# PENDING CONSIDERATION
def build_db(connection):
    '''
    Creates sqlite database file containing only the columns
    relevant for our use from the original vehicle csv.

    Input:
        full_csv: original data set holding
            superfluous columns
        connection: connection object for db file
    '''
    pertinent_data = ['id', 'make', 'model', 'year', 'VClass',
                      'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv',
                      'fuelCost08', 'fuelCostA08', 'fuelType',
                      'co2TailpipeGpm', 'co2TailpipeAGpm']
    df = pd.read_csv(URL, usecols=pertinent_data)
    df.set_index('id', drop=True, inplace=True)
    # IMPORTANT .to_sql cannot create a table with a primary key
    df.to_sql('vehicles', con=connection, if_exists='replace')

def trim_csv(full_data):
    '''
    Creates lightweight csv containing only the columns
    that will actually see use from the original vehicle csv.

    Input: full_data (csv) original data set holding
        superfluous columns
    
    Returns: new csv file containing only specific columns
        to feed into our sqlite table
    '''
    pertinent_data = ['id', 'make', 'model', 'year', 'VClass',
                      'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv',
                      'fuelCost08', 'fuelCostA08', 'fuelType',
                      'co2TailpipeGpm', 'co2TailpipeAGpm']
    df = pd.read_csv(full_data, usecols=pertinent_data)
    df.to_csv('trimmed.csv', index=False)

def csv_to_sql():
    database = "cscc.db"
    conn = sqlite3.connect(database)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS vehicles (CO2_A REAL, CO2 REAL,"
              " fuel_cost INTEGER, fuel_cost_A INTEGER,"
              " fuel_type varchar(200), hlv INTEGER, hpv INTEGER, id INTEGER,"
              " lv2 INTEGER, lv4 INTEGER, make varchar(200),"
              " model varchar(200), pv2 INTEGER, pv4 INTEGER,"
              " v_class varchar(200), year INTEGER)")

    subprocess.call(["sqlite3", database, ".separator ','",
                     ".import trimmed.csv vehicles"])
    
    return conn

def year_input_helper():
    '''
    Repeatedly asks user for input regarding car production
    year. Will not accept if year is not an integer or year
    given is not within a certain bound of the dataset.

    Returns: year - user inputted value for their car
    '''
    while True:
        try:
            year = input("Enter car's production year "
                         "(Optional, but recommended): ")
            if not year:
                return year
            year = int(year)
            if (YEAR_LB <= year <= YEAR_UB):
                return year
            print("Value is not within data bounds. Try again.")
        except ValueError:
            print("Value is not an integer. Try again.")

# WIP
def get_user_input(cursor):
    '''
    Creates a dictionary with user car information
    needed for look up as well as daily miles estimation
    '''
    # Saves user input
    make = input("Enter car's make: ")
    while not make:
        print("This field is required. Try again.")
        make = input("Enter car's make: ")
    model = input("Enter car's model (Optional, but recommended): ")
    year = year_input_helper()
    
    # If input doesn't match database, builds query based on
    # filled fields returning likely intended candidates
    required = 'SELECT make, model, year FROM vehicles WHERE make LIKE ?'
    model_option = ''
    year_option = ''
    params = ('%' + make + '%',)
    if model:
        model_option = ' AND model LIKE ?'
        params += ('%' + model + '%',)
    if year:
        year_option = ' AND year BETWEEN ? AND ?'
        lb, ub = year - YEAR_TOLERANCE, year + YEAR_TOLERANCE
        params += (lb, ub)
    query = required + model_option + year_option

    # Displays candidates in readable format for future selection
    print("Now displaying results 10 at a time.")
    next = ''
    cursor.execute(query, params)
    results = True
    i = 1
    while next != 'Q' and results:
        results = cursor.fetchmany(10)
        for row in results:
            print(row)
        print("Page " + str(i))
        next = input("Enter Q to stop or any other key to continue: ")
        i += 1

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

def go():
    '''
    Main program, takes users input (their current
    car and daily miles estimation) to compare their
    annual carbon emissions and spendings to that of
    other drivers. Program will then make recommendations
    of necessary milage reduction, or potential new car
    purchases/(public transportation use)
    '''
    full_csv = get_data(URL)
    trim_csv(full_csv)
    conn = csv_to_sql()
    #cscc_db = sqlite3.connect('cscc.db')
    #build_db(cscc_db)
    c = conn.cursor()
    get_user_input(c)
    conn.close()

if __name__ == "__main__":
    go()
