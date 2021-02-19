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
import questionary

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

PERTINENT_DATA = ['id', 'make', 'model', 'year', 'VClass',
                  'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv',
                  'fuelCost08', 'fuelCostA08', 'fuelType',
                  'co2TailpipeGpm', 'co2TailpipeAGpm']

MILES_PER_HOUR = 30 #needs to be edited
SELECT_CMD = ("SELECT co2TailpipeGpm, fuelCost08,"
              " fuelCostA08, fuelType FROM vehicles ")
WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"


def build_db(connection):
    '''
    Creates sqlite database file containing only the columns
    relevant for our use from the original vehicle csv.

    Input:
        full_csv: original data set holding
            superfluous columns
        connection: connection object for db file
    '''
    df = pd.read_csv(URL, usecols=PERTINENT_DATA, index_col='id', engine='c')
    # IMPORTANT .to_sql cannot create a table with a primary key
    df.to_sql('vehicles', con=connection, if_exists='replace')

# WIP
def get_user_input(cursor):
    '''
    Creates a dictionary with user car information
    needed for look up as well as daily miles estimation
    '''
    make_query = 'SELECT DISTINCT make FROM vehicles'
    make_results = cursor.execute(make_query).fetchall()
    make_results = [i[0] for i in make_results]
    #'SELECT EXISTS(SELECT 1 FROM myTbl WHERE u_tag="tag")'
    make_ans = questionary.autocomplete("What is your car's make?\n",
                                        choices=make_results).ask()

    mod_year_query = 'SELECT DISTINCT model, year FROM vehicles WHERE make = ?'
    mod_year_results = cursor.execute(mod_year_query, (make_ans,)).fetchall()
    mod_year_results = [' '.join((i, str(j))) for i, j in mod_year_results]
    mod_year_ans = questionary.autocomplete('What about model and year?\n',
                                            choices=mod_year_results).ask()
    print(' '.join([make_ans, mod_year_ans]))

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
    # Creates database if none already exists, skips this
    # computationally expensive processes otherwise.
    try:
        conn = sqlite3.connect('file:cscc.db?mode=rw', uri=True)
    except sqlite3.OperationalError:
        print('Local Database not found\n'
              'Creating database...')
        conn = sqlite3.connect('cscc.db')
        build_db(conn)
    cursor = conn.cursor()
    get_user_input(cursor)
    cursor.close()
    conn.close()

if __name__ == "__main__":
    go()
