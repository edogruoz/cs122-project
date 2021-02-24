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
import pandas as pd
#import questionary as q
#from questionary import ValidationError
#from questionary import Style

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

PERTINENT_DATA = ['id', 'make', 'model', 'year', 'VClass',
                  'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv',
                  'fuelCost08', 'fuelCostA08', 'fuelType',
                  'co2TailpipeGpm', 'co2TailpipeAGpm']

MILES_PER_HOUR = 30 #needs to be edited
SELECT_CMD = ("SELECT co2TailpipeGpm, fuelCost08,"
              " fuelCostA08, fuelType FROM vehicles ")
WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"

AVG_EMISSION = 4600000
"""
# Style options for terminal questions
custom_style = Style([
    ('qmark', 'fg:#A0E8AF bold'),       # token in front of the question
    ('question', 'fg:#EDEAD0 bold'),    # question text
    ('answer', 'fg:#27BB6F bold'),      # submitted answer text behind the question
    ('pointer', 'fg:#673ab7 bold'),     # pointer used in select and checkbox prompts
    ('highlighted', 'fg:#673ab7 bold'), # pointed-at choice in select and checkbox prompts
    ('selected', 'fg:#EDEAD0'),         # style for a selected item of a checkbox
    ('separator', 'fg:#cc5454'),        # separator in lists
    ('instruction', ''),                # user instructions for select, rawselect, checkbox
    ('text', ''),                       # plain text
    ('disabled', 'fg:#858585 italic')   # disabled choices for select and checkbox prompts
])
"""
def build_db(connection):
    '''
    Creates sqlite database file containing only the columns
    relevant for our use from the original vehicle csv.
    Fetches csv directly from constant URL and filters by
    constant PERTINENT_DATA.

    Input:
        connection: connection object for db file
    '''
    df = pd.read_csv(URL, usecols=PERTINENT_DATA, index_col='id', engine='c')
    # IMPORTANT .to_sql cannot create a table with a primary key
    df.to_sql('vehicles', con=connection, if_exists='replace')

# Used as questionary parameters to reject user input
def autoc_validator(text, cursor, query):
    '''
    Checks if the car details being inputted are valid,
    does not let user submit if it isn't in the local database.

    Inputs:
        text: string of the user's input, updates as it changes
            allowing for real time validation, unlike python's input()
        cursor: cursor object for database we will be querying
        query: string which is checked to determine what car detail
            to query for validation, the make or the model and year

    Returns: True if valid, else raises validation error
        (A little unorthodox vs just returning bools, but this allows
        error msg to show up in prompt properly)
    '''
    if query == 'make':
        exists_query = 'SELECT EXISTS (SELECT 1 FROM vehicles WHERE make = ?)'
    elif query == 'm_y':
        exists_query = ('SELECT EXISTS (SELECT 1 FROM vehicles '
                        'WHERE model || " " || year = ?)')
    exists = cursor.execute(exists_query, (text,)).fetchone()[0]
    if not exists:
        raise ValidationError(
            message='Current entry does not match database!'
        )

    return True

def txt_validator(text):
    '''
    Checks if use_miles is a non-negative number for
    validation.

    Inputs: text - string of the user's input, updates as it changes
        allowing for real time validation, unlike python's input()
    
    Returns: True if valid, else raises validation error
        (A little unorthodox vs just returning bools, but this allows
        error msg to show up in prompt properly)
    '''
    try:
        if float(text) < 0:
            raise ValidationError(
                message='Entry must be non-negative!'
            )
    except ValueError:
        raise ValidationError(
            message='Entry must be a number!'
        ) from ValueError

    return True

# WIP
def get_user_input(cursor):
    '''
    Creates a dictionary with user car information
    needed for look up along with daily miles estimation
    and various preferences for car suggestion.

    Inputs: Cursor - cursor object for database we will be querying

    Returns: Input_dict - dictionary containing all submitted user details
    '''
    make_query = 'SELECT DISTINCT make FROM vehicles'
    make_results = cursor.execute(make_query).fetchall()
    make_results = sorted({tup[0] for tup in make_results})
    make_ans = q.autocomplete("What is your car's make?\n   ",
                              choices=make_results,
                              validate=(lambda text:
                                        autoc_validator(text, cursor, 'make')),
                              style=custom_style, qmark='⯁ ').ask()

    print()
    m_y_query = ('SELECT DISTINCT model || " " || year '
                 'FROM vehicles WHERE make = ?')
    m_y_results = cursor.execute(m_y_query, (make_ans,)).fetchall()
    m_y_results = sorted({tup[0] for tup in m_y_results})
    m_y_ans = q.autocomplete('What about model and year?\n   ',
                             choices=m_y_results,
                             validate=(lambda text:
                                       autoc_validator(text, cursor, 'm_y')),
                             style=custom_style, qmark='⯁ ').ask()
    
    print()
    use_miles = q.text('Estimation for daily miles driven?\n   ',
                       validate=lambda text: txt_validator(text),
                       style=custom_style, qmark='⯁ ').ask()
    model,_ , year = m_y_ans.rpartition(' ')
    input_dict = {'make': make_ans,
                  'model': model,
                  'year': int(year),
                  'use_miles': float(use_miles)}
    print('For debugging purposes:')
    print(input_dict)
    return input_dict

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

def get_recommendation(emission, gpm):
    rv = {}
    if emission < AVG_EMISSION:
        return
    rv["percent"] = str(round((emission - AVG_EMISSION) / emission * 100, 1)) + " percent"
    rv["per year,"] = str(round((emission - AVG_EMISSION)/gpm, 1)) + " miles"
    rv["per month,"] = str(round((emission/12 - AVG_EMISSION/12)/gpm, 1)) + " miles"
    rv["per week"] = str(round((emission/52 - AVG_EMISSION/52)/gpm, 1)) + " miles"
    
    l = ["On", "average,", "you", "should", "drive"]
    l2 = ["less"]

    for key, value in rv.items():
        l += [value] + l2
        if key == "percent":
            l[-1] = "less,"
            continue
        l += [key]
        if key == "per month,":
            l += ["and"]
    
    s = " ".join(l)
    s += "."
    
    return s

def go():
    '''
    Main program, takes users input (their current
    car and daily miles estimation) to compare their
    annual carbon emissions and spendings to that of
    other drivers. Program will then make recommendations
    of necessary milage reduction, or potential new car
    purchases/(public transportation use).
    '''
    # Creates database if none already exists, skips this
    # computationally expensive processes otherwise.
    # TODO: update local database efficiently if changes are made to url file
    try:
        conn = sqlite3.connect('file:cscc.db?mode=rw', uri=True)
    except sqlite3.OperationalError:
        print('Local Database not found.\n'
              'Creating database...')
        conn = sqlite3.connect('cscc.db')
        build_db(conn)
    cursor = conn.cursor()
    get_user_input(cursor)
    cursor.close()
    conn.close()

if __name__ == "__main__":
    go()
