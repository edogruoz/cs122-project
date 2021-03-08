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
from sqlite3.dbapi2 import Error
import pandas as pd
import questionary as q
from questionary import ValidationError
from questionary import Style
import re
import urllib3
import bs4
import certifi
import io

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

DATA_COLS = ['id', 'make', 'model', 'year', 'trany', 'drive', 'cylinders',
             'VClass', 'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv', 'fuelCost08',
             'fuelCostA08', 'fuelType', 'co2TailpipeGpm', 'co2TailpipeAGpm']

MILES_PER_HOUR = 30 #needs to be edited
SELECT_CMD = ("SELECT co2TailpipeGpm, fuelCost08,"
              " fuelCostA08, fuelType FROM vehicles ")
WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"

AVG_EMISSION = 4600000
AVERAGE_CO2 = [89038.5]   #g/week
CAR_LIMIT = 20 #number of cars to reduce to before checking prices, can lower
MIN_LIMIT = 3

# Style options for terminal questions
q_style = Style([
    ('qmark', 'fg:#A0E8AF'),            # token in front of the question
    ('question', 'fg:#EDEAD0 bold'),    # question text
    ('answer', 'fg:#27BB6F bold'),      # submitted answer text behind the question
    ('pointer', 'fg:#A0E8AF bold'),     # pointer used in select and checkbox prompts
    ('highlighted', 'fg:#A0E8AF bold'), # pointed-at choice in select and checkbox prompts
    ('selected', 'fg:#EDEAD0 bold'),    # style for a selected item of a checkbox
    ('separator', 'fg:#cc5454'),        # separator in lists
    ('instruction', ''),                # user instructions for select, rawselect, checkbox
    ('text', ''),                       # plain text
    ('disabled', 'fg:#858585 italic')   # disabled choices for select and checkbox prompts
])

alert_style = Style([
    ('qmark', 'fg:#CF5050'),            # token in front of the question
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

def build_db(connection):
    '''
    Creates sqlite database file containing only the columns
    relevant for our use from the original vehicle csv.
    Fetches csv directly from constant URL and filters by
    constant DATA_COLS.

    Input:
        connection: connection object for db file
    '''
    df = pd.read_csv(URL, usecols=DATA_COLS, index_col='id', engine='c')
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

def unique_helper(cursor, col_str, param_tup, add=('', ())):
    '''
    '''
    uniq_query = ('SELECT ' + col_str + ' FROM vehicles ' + WHERE_CMD + add[0])
    uniq_results = cursor.execute(uniq_query, param_tup + add[1]).fetchall()
    uniq_results = {str(tup[0]) for tup in uniq_results}
    uniq = len(uniq_results) == 1

    return uniq, list(uniq_results)

# WIP
def get_user_input(conn):
    '''
    Creates a dictionary with user car information
    needed for look up along with daily miles estimation
    and various preferences for car suggestion.

    Inputs: Conn - connection object for database we will be querying

    Returns: Input_dict - dictionary containing all submitted user details
    '''
    cursor = conn.cursor()
    make_query = 'SELECT DISTINCT make FROM vehicles'
    make_results = cursor.execute(make_query).fetchall()
    make_results = sorted({tup[0] for tup in make_results})
    # Note, validate function must be passed in as lambda to work.
    # possible consequence of the internal validator class within questionary?
    make_ans = q.autocomplete("What is your car's make?\n   ",
                              choices=make_results,
                              validate=(lambda text:
                                        autoc_validator(text, cursor, 'make')),
                              style=q_style, qmark='⯁ ').ask()

    m_y_query = ('SELECT DISTINCT model || " " || year '
                 'FROM vehicles WHERE make = ?')
    m_y_results = cursor.execute(m_y_query, (make_ans,)).fetchall()
    m_y_results = sorted({tup[0] for tup in m_y_results})
    m_y_ans = q.autocomplete('What about model and year?\n   ',
                             choices=m_y_results,
                             validate=(lambda text:
                                       autoc_validator(text, cursor, 'm_y')),
                             style=q_style, qmark='\n⯁ ').ask()
    model,_ , year = m_y_ans.rpartition(' ')

    ans_tup = (make_ans, model, int(year))
    uniq, id_lst = unique_helper(cursor, 'id', ans_tup)
    id_ = id_lst[0]
    c_msg = ('Your particular car has some variants, would you like to be '
             'more specific?\n   You may be prompted to choose transmission, '
             ' number of cylinders, or drive type.\n   Recommended only if you '
             'are comfortable with these more advanced options.\n   '
             '(Skipping defaults to No.)\n   ')
    advanced = q.confirm(c_msg, default=False, style=alert_style,
                         qmark='\n❗').skip_if(uniq).ask()

    if advanced:
        t_uniq, t_results = unique_helper(cursor, 'trany', ans_tup)
        t_ans = q.select("Which matches your car's transmission?\n   ",
                         choices=sorted(t_results) + ['Not Sure'], style=q_style,
                         qmark='\n⯁ ').skip_if(t_uniq).ask()

        if t_ans in ['Not Sure', None]:
            trans, t_ans = '', ()
        else:
            trans, t_ans = ' AND trany = ?', (t_ans,)
        c_uniq, c_results = unique_helper(cursor, 'cylinders', ans_tup, (trans, t_ans))
        c_ans = q.select("Which matches your car's cylinder count?\n   ",
                         choices=sorted(c_results) + ['Not Sure'], style=q_style,
                         qmark='\n⯁ ').skip_if(c_uniq).ask()

        if c_ans in ['Not Sure', None]:
            cyl, c_ans = '', ()
        else:
            cyl, c_ans = ' AND cylinders = ?', (c_ans,)
        d_uniq, d_results = unique_helper(cursor, 'drive', ans_tup, (trans + cyl, t_ans + c_ans))
        d_ans = q.select("Which matches your car's drive type?\n   ",
                         choices=sorted(d_results) + ['Not Sure'], style=q_style,
                         qmark='\n⯁ ').skip_if(d_uniq).ask()

        if d_ans in ['Not Sure', None]:
            drive, d_ans = '', ()
        else:
            drive, d_ans = ' AND drive = ?', (d_ans,)
        
        id_query = 'SELECT id FROM vehicles ' + WHERE_CMD + trans + cyl + drive
        id_ = cursor.execute(id_query, ans_tup + t_ans + c_ans + d_ans).fetchone()

    input_dict = {'id': id_,
                  'make': make_ans,
                  'model': model,
                  'year': int(year)}

    use_miles = q.text('Estimation for weekly miles driven?\n   ',
                       validate=lambda text: txt_validator(text),
                       style=q_style, qmark='\n⯁ ').ask()
    
    input_dict['use_miles'] = float(use_miles)
    print('For debugging purposes:')
    print(input_dict)
    cursor.close()

    return input_dict

def rank_pref(conn, input_dict):
    '''
    '''
    CHOICES = ['Make', 'Year', 'Vehicle Class', 'Fuel Type',  'Passenger capacity', 'Luggage Capacity', 'Stop Ranking']
    print('We will now ask you to rank which attributes you like most about your current car.\n'
          'These choices will be taken into consideration for car recommendation.\n'
          "You may rank until you feel you have no more preferences or until you've exhausted all options.")
    i = 1
    pref = ''
    ranking_dict = dict()
    while len(CHOICES) > 2:
        pref = q.select('Choose preference: ', choices=CHOICES,
                        style=q_style, qmark='\n' + str(i)).ask()
        if pref == 'Stop Ranking':
            break
        CHOICES.remove(pref)
        ranking_dict[i] = pref
        i += 1
    if len(CHOICES) == 2:
        ranking_dict[i] = CHOICES[0]

    return ranking_dict

def get_emissions(input_dict, vehicles):
    make = input_dict["make"]
    model = input_dict["model"]
    year = input_dict["year"]
    array = [make, model, year]

    if input_dict["use_miles"]:
        use = input_dict["use_miles"]
    else:
        use = input_dict["use_hours"]
        use = MILES_PER_HOUR * use

    s = "SELECT co2TailpipeGpm, co2TailpipeAGpm FROM vehicles " + WHERE_CMD

    db = sqlite3.connect(vehicles)
    c = db.cursor()
    r = c.execute(s, array)
    rv = r.fetchall()
    db.close

    if rv:
        gpm, agpm = rv[0]
        if agpm == 0:
            weekly_emission = gpm * use
        else:
            weekly_emission = ((gpm + agpm) / 2) * use
        yearly_emission = weekly_emission * 52
        return yearly_emission

    # Raise error as there was nothing returned from the db
    raise Error('No emission data found in the database for the given make and model.')


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

def get_fuel_price(db, car_id, no_miles):
    '''
    Gives the money spent on fuel for a given car and
    a given number of miles
    '''

    s1 = "SELECT fuelCost08, fuelCostA08 FROM vehicles WHERE id = ?"

    db = sqlite3.connect(db)
    c = db.cursor()
    r = c.execute(s1, car_id)
    rv = r.fetchall()
    db.close

    fuel1_cost, fuel2_cost = rv

    if fuel2_cost:
        cost = (fuel1_cost + fuel2_cost) / 2
    else:
        cost = fuel1_cost

    return (cost / YEARLY_MILES) * no_miles

def co2_emission(co2_1, co2_2, miles):
    '''
    Calculates co2 emissions with the given mile, 
      to be used in sqlite
    '''

    if co2_2 != 0:
        co2 = (co2_1 + co2_2)/2
    else:
        co2 = co2_1
    
    return co2 * miles

def recommend_cars(db, input_dict, ranking_dict, id):
    '''
    Determines cars to recommend that have less than
    average emission and qualities input by the user

    '''
    db = sqlite3.connect(db)
    c = db.cursor()
    db.create_function("co2_emission", 3, co2_emission)
    miles = input_dict["use_miles"]

    s1 = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, \
            co2_emission(vehicles.co2TailpipeGpm, vehicles.co2TailpipeAGpm, " +  str(miles) + ") \
            AS co2_emission, year FROM vehicles WHERE co2_emission <= ?"
    
    alt_s = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, \
             year FROM vehicles" #to be potentially used later 
            
    a = c.execute(s1, AVERAGE_CO2)

    df = pd.DataFrame(a.fetchall(), columns=["id", "make","model", "pv2", "pv4", "hpv", "lv2", \
                                            "lv4", "hlv", "fuelType", "VClass", "co2_emission", "year"])

    s2 = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, year FROM vehicles WHERE id = ?"

    old_car = c.execute(s2, [str(id)])
    car_id, car_make, car_model, car_pv2, car_pv4, car_hpv, \
        car_lv2, car_lv4, car_hlv, car_fuelType, car_VClass, year = old_car.fetchall()[0]

    car_lv = max(car_lv4, car_hlv, car_lv2) #taking the max since some will have 0 as entries
    car_pv = max(car_pv2, car_pv4, car_hpv)

    match_dict = {"make":car_make, "VClass":car_VClass, \
        "fuelType":car_fuelType, "year": year, "luggage_volume": car_lv, "passenger_volume": car_pv}

    car_dict = {"id":car_id, "make":car_make,"model": car_model, "pv2": car_pv2, "pv4":car_pv4,"hpv":car_hpv,\
        "lv2":car_lv2, "lv4":car_lv4, "hlv":car_hlv, "fuelType":car_fuelType, "VClass":car_VClass, "year":year}

    df = df.append(car_dict, ignore_index=True) #important for the price function for this to be the LAST row
    
    for i in range(1, len(ranking_dict)+1):
        of_interest = ranking_dict[i]
        if of_interest  in ["make", "VClass", "fuelType"]:
            new_df = df[df[of_interest] == match_dict[of_interest]]
        elif of_interest == "year":
            new_df = df[(df[of_interest] >= match_dict[of_interest]
             - 5) & (df[of_interest] <= match_dict[of_interest] + 5)]
        else:
            if of_interest == "luggage_volume": #choosing the max for comparison to ignore entries of 0
                if car_lv == 0:
                    car_lv = get_volume(c, alt_s, id, "lv")
                if car_lv == 0:
                    continue
                df = process_df(df, "lv")
                new_df = df[(df[["lv4", "hlv", "lv2"]].max(axis=1) >= 
                car_lv * 0.95) & (df[["lv4", "hlv", "lv2"]
                ].max(axis=1) <= car_lv * 1.05)]
            else:
                if car_pv == 0:
                    car_pv = get_volume(c, alt_s, id, "pv")
                if car_pv == 0:
                    continue
                df = process_df(df, "pv")
                new_df = df[(df[["pv4", "hpv", "pv2"]].max(axis=1) >= 
                car_pv * 0.95) & (df[["pv4", "hpv", "pv2"]
                ].max(axis=1) <= car_pv * 1.05)]
        if len(new_df) <= MIN_LIMIT:  # discard the new filtering if the resulting number of cars is too small
            continue
        df = new_df
        if len(df) <= CAR_LIMIT:  # break the loop if we have a small enough number of cars
            break
    
    return df


def get_volume(cursor, string, id, type_):
    '''
    Get luggage or passenger volume of the input car if it is missing
    '''
    if type_ == "lv":
        lst = ["lv2", "lv4", "hlv"]
    else:
        lst = ["pv2", "pv4", "hpv"]

    b = cursor.execute(string)
    new_df = pd.DataFrame(b.fetchall(), columns = ["id", "make",
        "model", "pv2", "pv4", "hpv", "lv2", "lv4", "hlv", 
        "fuelType", "VClass", "year"])
    row = new_df[new_df["id"] == id]
    new_df = process_df(new_df, type_, row)
    new_row = new_df[new_df["id"] == id]
    car_v = new_row[lst].max(axis=1).item()

    return car_v


def process_df(df, type_, df2=False):
    '''
    Given a df, fill rows with no volume info with info from cars
    of the same model
    '''
    if isinstance(df2, bool):
        df2 = df

    if type_ == "pv":
        missing_pv = df2[df2[["pv2", "pv4", "hpv"]].max(axis=1) == 0]
        df = helper_process_df(df, missing_pv, "pv")
    elif type_ == "lv":
        missing_lv = df2[df2[["lv2", "lv4", "hlv"]].max(axis=1) == 0]
        df = helper_process_df(df, missing_lv, "lv")
    
    return df


def helper_process_df(df, df2, type_):
    '''
    Helper function for process_df
    '''
    if type_ == "pv":
        cols = ["pv2", "pv4", "hpv"]
    else:
        cols = ["lv2", "lv4", "hlv"]

    df["first_word"] = pd.read_table(io.StringIO(df["model"].to_csv(None,
        index=None)), sep=" ", usecols=[0])

    for _, row in df2.iterrows():
        id = row["id"]
        make = row["make"]
        model = row["model"]
        model_str = model.split()[0]
        year = row["year"]
        
        alternatives = df[(df["make"] == make) & (df["first_word"] == model_str
            ) & (df["year"].between(year - 4, year + 4)) & (df["id"] != id) & (
            df[cols].max(axis=1) > 0)]

        if len(alternatives) == 0:
            continue

        for col in cols:
            series = alternatives[(alternatives[col] > 0)][col].dropna()
            if not len(series):
                continue
            avg = series.mean().item()
            ind = df[df["id"] == id].index.values.astype(int)[0]
            df.at[ind, col] = avg

    df = df.drop(["first_word"], axis=1)

    return df


def get_info_for_price(data_str):
    '''
    data_str: dictionary or pandas df row
    '''
    make = data_str["make"]
    model_lst = data_str["model"].split()
    possible_models = ["-".join(model_lst).lower(), model_lst[0].lower()]
    if len(model_lst) >= 2:
            possible_models +=  ["-".join(model_lst[:2]).lower()]
    year = data_str["year"]

    return make, possible_models, year


def get_car_prices(car_df, input_dict):
    '''
    Crawls prices for the recommended cars and the user's car
      from kbb. 
    
    Inputs:
        car_df (pd.DataFrame): dataframe of cars to be recommended
        input_dict
    
    Returns:
        price_dict (dict): a dictionary with car id as the key and a 
          tuple of (make, model, year, price) as the value
        no_price_found (dict): a dictionary with car id as the key and a 
          tuple of (make, model, year) as the value for cars whose 
          prices could not be found in kbb
        old_car_price: price of the user's own car, None if not found
    '''
    

    pm = urllib3.PoolManager(
       cert_reqs='CERT_REQUIRED',
       ca_certs=certifi.where())
    
    price_dict = {}
    no_price_found = {}
    old_car_price = None

    for i, row in car_df.iterrows():
        make, possible_models, year = get_info_for_price(row)
        if year < 1992 and i != len(new_df) - 1:
            no_price_found[row["id"]] = (make, model, year)
            continue
        for i, model in enumerate(possible_models):
            myurl = "https://www.kbb.com/{}/{}/{}/".format(make, model, year)
            html = pm.urlopen(url=myurl, method="GET").data
            soup = bs4.BeautifulSoup(html, features="html.parser")
            title = soup.find_all("title")[0].text
            if ("Find Your Perfect Car" not in title) and ("Kelley Blue Book | Error" not in title):  #these indicate that there was no exact match
                break
        if ("Find Your Perfect Car" in title) or ("Kelley Blue Book | Error" in title) or (str(year) not in title):
            no_price_found[row["id"]] = (make, model, year)
            continue
        price_text = soup.find_all("script", attrs={"data-rh":"true"})[-1].text
        m =  re.findall('"price":"([0-9]+)"', price_text)[0]
        if i == len(new_df) - 1:
            old_car_price = m 
        else:
            price_dict[row["id"]] = (make, model, year, m) 
    
    return price_dict, no_price_found, old_car_price


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
    input_dict = get_user_input(conn)

    # Calculate and print the emissions for debugging
    emissions = get_emissions(input_dict, 'cscc.db')
    print('Yearly CO2 emission: ' + str(emissions) + ' grams.')
    print()

    ranking_dict = rank_pref(conn, input_dict)
    print('Debug ranking: ')
    print(ranking_dict)

    conn.close()

if __name__ == "__main__":
    go()
