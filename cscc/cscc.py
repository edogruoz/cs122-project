# CSCC Project
#
# CMSC 12200
#
# Efe Dogruoz, Ebru Ermis, Mey Abdullahoglu, Kevin Ramirez

import io
import re
import bs4
import urllib3
import certifi
import sqlite3
from sqlite3.dbapi2 import Error
import pandas as pd
import numpy as np

import questionary as q
from questionary import ValidationError
from questionary import Style

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

DATA_COLS = ['id', 'make', 'model', 'year', 'trany', 'drive', 'cylinders',
             'VClass', 'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv', 'fuelCost08',
             'fuelCostA08', 'fuelType', 'co2TailpipeGpm', 'co2TailpipeAGpm']

WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"

AVG_EMISSION = 4600000 #g/year
AVG_CO2 = 89038.5   #g/week
CAR_LIMIT = 20 #number of cars to reduce to before checking prices, can lower
MIN_LIMIT = 3
YEARLY_MILES = 15000

# Style options for terminal questions
S_CONFIG = [('qmark', 'fg:#A0E8AF'),             # token in front of the question
            ('question', 'fg:#EDEAD0 bold'),     # question text
            ('answer', 'fg:#27BB6F bold'),       # submitted answer text behind the question
            ('pointer', 'fg:#A0E8AF bold'),      # pointer used in select and checkbox prompts
            ('highlighted', 'fg:#A0E8AF bold'),  # pointed-at choice in select and checkbox prompts
            ('selected', 'fg:#EDEAD0 bold'),     # style for a selected item of a checkbox
            ('separator', 'fg:#cc5454'),         # separator in lists
            ('instruction', ''),                 # user instructions for select, rawselect, checkbox
            ('text', ''),                        # plain text
            ('disabled', 'fg:#858585 italic')]   # disabled choices for select and checkbox prompts


def build_db(connection):
    """
    Creates sqlite database file containing only the columns
    relevant for our use from the original vehicle csv.
    Fetches csv directly from constant URL and filters by
    constant DATA_COLS.

    Parameters:
        connection (obj): connection object for db file
    """
    df = pd.read_csv(URL, usecols=DATA_COLS, index_col='id', engine='c')
    # IMPORTANT .to_sql cannot create a table with a primary key
    df.to_sql('vehicles', con=connection, if_exists='replace')


def get_id(conn):
    """
    Extracts unique id from database by narrowing down candidates based
    on user provided information. Some cars continue to have variants
    even after all questions have been asked. For those that do, the
    first id fetched by the final query result is the one we will use.

    Parameters:
        conn (obj): connection to sqlite database we will be querying

    Returns:
        int: identifier for user's current car, used as a means to
            access other information related to their vehicle for
            future functions
    """
    c = conn.cursor()
    make_query = 'SELECT DISTINCT make FROM vehicles'
    make_results = c.execute(make_query).fetchall()
    make_results = sorted({tup[0] for tup in make_results})
    make_ans = q.autocomplete("What is your car's make?\n   ",
                              choices=make_results,
                              validate=(lambda text:
                                        autoc_validator(text, c, 'make')),
                              style=Style(S_CONFIG), qmark='⯁ ').ask()

    m_y_query = ('SELECT DISTINCT model, year '
                 'FROM vehicles WHERE make = ?')
    m_y_results = set(c.execute(m_y_query, (make_ans,)).fetchall())
    m_y_results = sorted(m_y_results, key=lambda tup: (tup[0], -tup[1]))
    m_y_results = [tup[0] + ' ' + str(tup[1]) for tup in m_y_results]
    m_y_ans = q.autocomplete('What about model and year?\n   ',
                             choices=m_y_results,
                             validate=(lambda text:
                                       autoc_validator(text, c, 'm_y')),
                             style=Style(S_CONFIG), qmark='\n⯁ ').ask()
    model,_ , year = m_y_ans.rpartition(' ')

    base_tup = (make_ans, model, int(year))
    id_query = f'SELECT id FROM vehicles {WHERE_CMD}'
    uniq_results = c.execute(id_query, base_tup).fetchall()
    uniq_results = [tup[0] for tup in uniq_results]
    id_ = uniq_results[0]
    uniq = len(uniq_results) == 1
    c_msg = ('Your particular car has some variants, would you like to be '
             'more specific?\n   You may be prompted to choose transmission, '
             'number of cylinders, or drive type.\n   Recommended only if '
             'you are comfortable with these more advanced options.\n   '
             '(Skipping defaults to No.)\n   ')
    advanced = q.confirm(c_msg, default=False,
                         style=Style(S_CONFIG + [('qmark', 'fg:#CF5050')]),
                         qmark='\n❗').skip_if(uniq).ask()

    if advanced:
        t_ans, _ = unique_helper(c, 'trany', 'transmission', base_tup)
        c_ans, _ = unique_helper(c, 'cylinders', 'number of cylinders',
                                 base_tup, [('trany', t_ans)])
        d_ans, cond = unique_helper(c, 'drive', 'drive type', base_tup,
                                    [('trany', t_ans), ('cylinders', c_ans)])
        if d_ans:
            cond += ' AND drive = ?'
        add_tup = tuple(val for val in (t_ans, c_ans, d_ans) if val)
        id_query = 'SELECT id FROM vehicles ' + WHERE_CMD + cond
        id_ = c.execute(id_query, base_tup + add_tup).fetchone()[0]
    c.close()
    return id_


def autoc_validator(text, cursor, query):
    """
    Checks if the car details being inputted are valid,
    does not let user submit if it isn't in the local database.

    Parameters:
        text (str): user's input, updates as it changes allowing
            for real time validation, unlike python's input()
        cursor (obj): cursor for database we will be querying
        query (str): checked to determine what car detail to query
            for validation, the make or the model and year

    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: Raises instead of returning False, this
            allows for questionary to properly display validator msg
    """
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


def unique_helper(c, col, col_desc, base_param, prev=[]):
    """
    Refines id search by checking if transmission, cylinder, or drive
    data is enough to uniquely identify a given car.

    Parameters:
        c (obj): cursor for current connection to database
        col (str): column we will query for uniqueness
        col_desc (str): modifies question string to best fit
            current query
        base_param (tup): make, model, year used as filters for
            query. These parameters are built upon as each
            successive question provides new information
        prev (lst): contains tuples of form
            (prev col queried, prev unique_helper result)
            needed so that later calls to this function may
            use new information to refine its query
    
    Returns:
        tup:ans (str) - the feature selected by the user that matches
            their current car. Can also be None if there is only one
            possible choice of that feature given the query
            restrictions or if user is unsure
            cond (str) - (used only the last time the function is
            called) saves WHERE clause to be used outside the function
    """
    add_cond, param_tup = '', ()
    prev = [tup for tup in prev if tup[1]]
    if prev:
        cond_tup, param_tup = zip(*prev)
        for cond in cond_tup:
            add_cond += f' AND {cond} = ?'
    uniq_query = f'SELECT {col} FROM vehicles {WHERE_CMD} {add_cond}'
    uniq_results = c.execute(uniq_query, base_param + param_tup).fetchall()
    uniq_results = {str(tup[0]) for tup in uniq_results}
    uniq = len(uniq_results) == 1
    ans = q.select(f"Which matches your car's {col_desc}?\n   ",
                         choices=sorted(uniq_results) + ['Not Sure'],
                         style=Style(S_CONFIG),
                         qmark='\n⯁ ').skip_if(uniq).ask()
    if ans == 'Not Sure':
        ans = None
    return ans, add_cond


def get_miles():
    """
    Asks user for estimation of their current weekly miles.
    Used to calculate their emission.

    Returns:
        float: user's estimated weekly milage
    """
    use_miles = q.text('Estimation for weekly miles driven?\n   ',
                       validate=lambda text: txt_validator(text),
                       style=Style(S_CONFIG), qmark='\n⯁ ').ask()
    return float(use_miles)


def txt_validator(text):
    """
    Checks if use_miles is a non-negative number for
    validation.

    Parameters:
        text (str): user's input, updates as it changes allowing
            for real time validation, unlike python's input()

    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: Raises instead of returning False, this
            allows for questionary to properly display validator msg
    """
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


def get_emissions(conn, id_, use_miles):
    """
    Retrieve yearly emissions for user's current vehicle based on
    their usage estimation and their car's co2 g/mile.

    Parameters:
        conn (obj): connection to sqlite database we will be querying
        id_ (int): unique identifier for user's current car
        use_miles (float): estimation for user's weekly milage

    Returns:
        tup: yearly co2 emissions in grams and gpm for use in
             get_cut_recommendation
    """
    c = conn.cursor()
    co2_query = ('SELECT co2TailpipeGpm, co2TailpipeAGpm '
                 'FROM vehicles WHERE id = ?')
    gpm, agpm = c.execute(co2_query, (id_,)).fetchone()
    c.close()
    if not (gpm or agpm):
        print('\nElectric Vehicle')
        return 0.0, 0.0
    if not agpm:
        return 52 * gpm * use_miles, gpm
    else:
        avg_gpm = (gpm + agpm) / 2
        return 52 * avg_gpm * use_miles, avg_gpm


def get_cut_recommendation(emission, gpm):
    """
    Get recommendation string for how much less the user has to drive
    per week to meet the average carbon emission value.

    Parameters:
        emission (float): yearly carbon emission of the user in grams.
        gpm (float): grams per mile value for input car.
    
    Returns:
        str: message containing how many miles less the user has to
            drive to meet average.
    """
    rv = {}
    if emission < AVG_EMISSION:
        return "Your carbon emission is below average."
    rv["percent"] = (str(round((emission - AVG_EMISSION) / emission * 100, 1))
                     + " percent")
    rv["per year,"] = str(round((emission - AVG_EMISSION)/gpm, 1)) + " miles"
    rv["per month,"] = (str(round((emission/12 - AVG_EMISSION/12)/gpm, 1))
                        + " miles")
    rv["per week"] = (str(round((emission/52 - AVG_EMISSION/52)/gpm, 1))
                      + " miles")

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


def rank_pref():
    """
    Ranks vehicle attributes that user cares most about from their
    current car. Uses this information to more accurately recommend
    a new vehicle.

    Returns:
        lst: elements are arranged in order of priority
    """
    CHOICES = ['Make', 'Year', 'Transmission', 'Vehicle Class', 'Fuel Type',
               'Passenger capacity', 'Luggage Capacity', 'Stop Ranking']
    DICT_MAP = {'Make': 'make', 'Year': 'year', 'Transmission': 'trany',
                'Vehicle Class': 'VClass', 'Fuel Type': 'fuelType',
                'Luggage Capacity': 'luggage_volume'}
    q.print('We will now ask you to rank which attributes you like most '
            'about your current vehicle.\nThese choices will be taken into '
            'consideration for car recommendation.\nYou may rank until you '
            "feel you have no more preferences or until you've exhausted all "
            'options.', style=S_CONFIG[1][1])

    i = 1
    pref = ''
    rank_order = []
    while len(CHOICES) > 2:
        pref = q.select('Choose preference: ', choices=CHOICES,
                        style=Style(S_CONFIG), qmark='\n' + str(i)).ask()
        if pref == 'Stop Ranking':
            break
        CHOICES.remove(pref)
        rank_order.append(pref)
        i += 1
    if len(CHOICES) == 2:
        rank_order.append(CHOICES[0])
    # Rename items in rank list to the less human readable col names
    return list((pd.Series(rank_order, dtype = 'object')).map(DICT_MAP))


def recommend_cars(conn, id_, use_miles, rank_order, gpm):
    """
    Determines and returns a list of cars to recommend that have less than
      average CO2 emissions with the number of miles inputted by the user.
      It filters for cars that are similar to the user's current car
      in terms of the attributes they choose 

    Parameters:
        conn (obj): connection to sqlite database we will be querying
        id_ (int): unique identifier for user's current car
        use_miles (float): estimation for user's weekly milage, 
          inputted by the user
        rank_order (lst): ordered list of attributes that the user
          cares most about from their current car and wants to be present
          in their new car
        gpm (float): grams of CO2 emitted per mile by the current car of the
          user
    
    Returns:
        pandas.DataFrame: dataframe with cars to recommend
    """
    if gpm == 0:
        return "Your carbon emission is 0 - no recommendations were found!"

    conn.create_function("co2_emission", 3, co2_emission)
    c = conn.cursor()

    current_co2 = (gpm * use_miles)

    s1 = (f'SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, '
          f'VClass, co2_emission(vehicles.co2TailpipeGpm, '
          f'vehicles.co2TailpipeAGpm, {str(use_miles)}) '
          f'AS co2_emission, year, trany FROM vehicles WHERE co2_emission <= '
          f'? AND co2_emission < ?')
    
    alt_s = ('SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, '
             'fuelType, VClass, year, trany FROM vehicles') #to be potentially used later
            
    params = [AVG_CO2, current_co2]
    a = c.execute(s1, params)

    df = pd.DataFrame(a.fetchall(),
                      columns=["id", "make","model", "pv2", "pv4", "hpv",
                               "lv2", "lv4", "hlv", "fuelType", "VClass",
                               "co2_emission", "year", "trany"])

    s2 = ('SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, '
          'VClass, year, trany FROM vehicles WHERE id = ?')

    old_car = c.execute(s2, [str(id_)])
    (car_id, car_make, car_model, car_pv2, car_pv4, car_hpv, car_lv2, car_lv4,
     car_hlv, car_fuelType, car_VClass, year, trany) = old_car.fetchall()[0]

    car_lv = max(car_lv4, car_hlv, car_lv2) #taking the max since some will have 0 as entries
    car_pv = max(car_pv2, car_pv4, car_hpv)

    match_dict = {"make":car_make, "VClass":car_VClass,
                  "fuelType":car_fuelType, "year": year,
                  "luggage_volume": car_lv, "passenger_volume": car_pv,
                  "trany": trany}

    car_dict = {"id":car_id, "make":car_make, "model": car_model,
                "pv2": car_pv2, "pv4":car_pv4,"hpv":car_hpv, "lv2":car_lv2,
                "lv4":car_lv4, "hlv":car_hlv, "fuelType":car_fuelType,
                "VClass":car_VClass, "year":year, "trany": trany}

    df = df.append(car_dict, ignore_index=True) #important for the price function for this to be the LAST row
    
    for of_interest in rank_order:
        if of_interest  in ["make", "VClass", "fuelType"]:
            new_df = df[df[of_interest] == match_dict[of_interest]]
        elif of_interest == "year":
            new_df = df[(df[of_interest] >= match_dict[of_interest] - 5)
                         & (df[of_interest] <= match_dict[of_interest] + 5)]
        elif of_interest == "trany":
            m = df["trany"].str.split(" ", expand=True).iloc[:, 0]
            new_d = pd.concat([df, m], axis=1)
            new_df = new_d[new_d.iloc[:, -1]
                           == match_dict[of_interest].split()[0]]
            new_df = new_df.drop(new_df.columns[-1], axis=1)
        else:
            if of_interest == "luggage_volume": #choosing the max for comparison to ignore entries of 0
                if car_lv == 0:
                    car_lv = get_volume(c, alt_s, id_, "lv")
                if car_lv == 0:
                    continue
                df = process_df(df, "lv")
                new_df = df[(df[["lv4", "hlv", "lv2"]].max(axis=1)
                             >= car_lv * 0.95)
                            & (df[["lv4", "hlv", "lv2"]].max(axis=1)
                               <= car_lv * 1.05)]
            else:
                if car_pv == 0:
                    car_pv = get_volume(c, alt_s, id_, "pv")
                if car_pv == 0:
                    continue
                df = process_df(df, "pv")
                new_df = df[(df[["pv4", "hpv", "pv2"]].max(axis=1)
                             >= car_pv * 0.95)
                            & (df[["pv4", "hpv", "pv2"]].max(axis=1)
                               <= car_pv * 1.05)]
        if len(new_df) <= MIN_LIMIT:  # discard the new filtering if the resulting number of cars is too small
            continue
        df = new_df
        if len(df) <= CAR_LIMIT:  # break the loop if we have a small enough number of cars
            break
    
    if len(df) > 20:  #dropping the original car, sampling, adding it again
        df = df.drop(index=df[df["id"] == id_].index)
        df = df.sample(n=20, random_state=1)
        df = df.append(car_dict, ignore_index=True)
    c.close()

    return df


def co2_emission(co2_1, co2_2, miles):
    """
    Calculates co2 emissions with the given number of miles
      based on an average value, to be used in the sqlite database.
    
    Parameters:
        co2_1 (float): emitted CO2 in grams/mile for 
          for the fuel type 1. If the car uses only 1 type
          of fuel, this is the only CO2 emission value
        co2_2 (float): emitted CO2 in grams/mile for 
          for the fuel type 1
        miles (float): estimation for user's weekly milage, 
          inputted by the user
    
    Returns:
        float: grams of CO2 emitted with the number of miles
          user inputted
    """
    if co2_2 != 0:
        co2 = (co2_1 + co2_2)/2
    else:
        co2 = co2_1
    return co2 * miles


def get_volume(c, string, id_, type_):
    """
    Get luggage or passenger volume of the input car if it is missing.

    Parameters:
        cursor (obj): cursor for database we will be querying
        string (str): query statement to excute
        id_ (int): unique identifier for user's current car

    Returns:
        float: volume in cubic feet
    """
    if type_ == "lv":
        lst = ["lv2", "lv4", "hlv"]
    else:
        lst = ["pv2", "pv4", "hpv"]

    b = c.execute(string)
    new_df = pd.DataFrame(b.fetchall(),
                          columns = ["id", "make", "model", "pv2", "pv4",
                                     "hpv", "lv2", "lv4", "hlv", "fuelType",
                                     "VClass", "year", "trany"])
    row = new_df[new_df["id"] == id_]
    new_df = process_df(new_df, type_, row)
    new_row = new_df[new_df["id"] == id_]
    car_v = new_row[lst].max(axis=1).item()

    return car_v


def process_df(df, type_, df2=False):
    """
    Given a df, volume type, and a second df, fill rows with no volume
    info with info from cars of the same model.

    Parameters:
        df (pd df): dataframe to use to get volume information of
            other cars.
        type_ (str): volume type to fill in. either "pv" for passenger
            volume or "lv" for luggage volume. 
        df2 (df): a second dataframe that contains rows of cars whose
            volume values need to be filled in. Defaults no False, in
            which case df is used for this parameter.
    
    Returns:
        df: pd dataframe with rows with missing volume information
            have been filled in based on similar cars (when possible).
    """
    if isinstance(df2, bool): # means a second df has not been entered
        df2 = df
    if type_ == "pv":
        missing_pv = df2[df2[["pv2", "pv4", "hpv"]].max(axis=1) == 0]
        df = helper_process_df(df, missing_pv, "pv")
    elif type_ == "lv":
        missing_lv = df2[df2[["lv2", "lv4", "hlv"]].max(axis=1) == 0]
        df = helper_process_df(df, missing_lv, "lv")
    return df


def helper_process_df(df, df2, type_):
    """
    Helper function for process_df.

    Parameters:
        df (pd df): dataframe to use to get volume information of
            other cars.
        df2 (df): a second dataframe that only contains rows with
            missing volume information of the relevant type.
        type_ (str): volume type to fill in. either "pv" for
            passenger volume or "lv" for luggage volume. 
    
    Returns:
        df (pd df): pd dataframe with rows with missing volume
            information have been filled in based on similar
            cars (when possible).
    """
    if type_ == "pv":
        cols = ["pv2", "pv4", "hpv"] # columns of interest
    else:
        cols = ["lv2", "lv4", "hlv"]

    df["first_word"] = pd.read_table(io.StringIO(df["model"].to_csv(None,
        index=None)), sep=" ", usecols=[0]) # separate the model column by word, take the first word

    for _, row in df2.iterrows():
        id = row["id"]
        make = row["make"]
        model = row["model"]
        model_str = model.split()[0] # first word of model name
        year = row["year"]
        
        alternatives = df[(df["make"] == make)
                          & (df["first_word"] == model_str)
                          & (df["year"].between(year - 4, year + 4))
                          & (df["id"] != id)
                          & (df[cols].max(axis=1) > 0)] # similar cars whose volume information is not missing

        if len(alternatives) == 0:
            continue

        for col in cols: # checking for each column within columns of interest
            series = alternatives[(alternatives[col] > 0)][col].dropna()
            if not len(series):
                continue
            avg = series.mean().item() 
            ind = df[df["id"] == id].index.values.astype(int)[0] # find index of car of interest
            df.at[ind, col] = avg

    df = df.drop(["first_word"], axis=1)

    return df


def get_savings(conn, id_, use_miles, df):
    """
    Given a df from recommend_cars(), and the user's own car's id,
    calculate the fuel costs and savings and add them to the df
    returned.

    Parameters:
        conn (obj): connection to sqlite database we will be querying
        id_ (int): unique identifier for user's current car
        use_miles (float): estimation for user's weekly milage
        df (df): filtered dataframe of recommended cars we will add to
    
    Returns:
        df: same dataframe with new columns
    """
    s = ('SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, '
         'VClass, year, trany FROM vehicles WHERE id = ?')
    old_weekly_cost = get_fuel_price(id_, conn, use_miles)
    old_yearly_cost = old_weekly_cost * 52
    df.loc[:, "weekly_cost"] = df.id.apply(get_fuel_price,
                                           args=(conn, use_miles))
    df.loc[:, "yearly_cost"] = df.loc[:, "weekly_cost"] * 52
    df.loc[:, "weekly_savings"] = old_weekly_cost - df.loc[:, "weekly_cost"]
    df.loc[:, "yearly_savings"] = old_yearly_cost - df.loc[:, "yearly_cost"]
    return df


def get_fuel_price(id_, conn, use_miles):
    """
    Gives the money spent on fuel for a given car and
    a given number of miles

    Parameters:
        conn (obj): connection to sqlite database we will be querying
        id_ (int): unique identifier a car
        use_miles (float): estimation for user's weekly milage, 
            inputted by the user
    
    Returns:
        float:
    """
    s1 = "SELECT fuelCost08, fuelCostA08 FROM vehicles WHERE id = ?"
    c = conn.cursor()
    r = c.execute(s1, [str(id_)])
    rv = r.fetchall()
    c.close()

    fuel1_cost, fuel2_cost = rv[0]
    if fuel2_cost:
        cost = (fuel1_cost + fuel2_cost) / 2
    else:
        cost = fuel1_cost
    return (cost / YEARLY_MILES) * use_miles


def get_car_prices(car_df):
    """
    Crawls prices for the recommended cars and the user's car
    from kbb and adds them as columns to the inputted dataframe.
    Tries different options for model names to find a match and asks
    the user for an estimation if the price for their old car is
    not found.
    
    Parameters:
        car_df (pd.DataFrame): dataframe of cars to be recommended
    
    Returns:
        car_df (pd.DataFrame): dataframe of cars to be recommended
            with the added price and difference columns
        old_car_price (float): price of the user's current car
    """
    car_df["price"] = np.nan

    pm = urllib3.PoolManager(
       cert_reqs='CERT_REQUIRED',
       ca_certs=certifi.where())
    
    old_car_price = None
    car_df = car_df.reset_index()
    car_df.loc[:, "model"] = car_df.loc[:, "model"].str.replace("/", " ")

    for i, row in car_df.iterrows():
        make, possible_models, year = get_info_for_price(row)
        if year < 1992 and i != len(car_df) - 1:
            continue
        for j, model in enumerate(possible_models):
            myurl = "https://www.kbb.com/{}/{}/{}/".format(make, model, year)
            html = pm.urlopen(url=myurl, method="GET").data
            soup = bs4.BeautifulSoup(html, features="html.parser")
            title = soup.find_all("title")[0].text
            if (("Find Your Perfect Car" not in title)
                and ("Kelley Blue Book | Error" not in title)):
                break
        if (("Find Your Perfect Car" in title)
            or ("Kelley Blue Book | Error" in title)
            or (str(year) not in title)):
            continue
        price_text = soup.find_all("script",
                                   attrs={"data-rh":"true"})[-1].text
        m =  re.findall('"price":"([0-9]+)"', price_text)[0]
        if i == len(car_df) - 1:
            old_car_price = m
        car_df.loc[i, "price"] = float(m)
    
    old_car_price = q.text('No associated price could be found for your car.'
                           '\n   What do you believe your car is worth?\n   ',
                           validate=lambda text: txt_validator(text),
                           style=Style(S_CONFIG + [('qmark', 'fg:#CF5050')]),
                           qmark='\n❗').skip_if(old_car_price is not None,
                                                old_car_price).ask()
    car_df["difference"] = (float(old_car_price)
                            - car_df.price[car_df.price.notna()])
    car_df = car_df.drop(car_df.tail(1).index)
    return car_df, old_car_price


def get_info_for_price(data_str):
    """
    Extracts the needed information (make, model, year)
    from the given row of the dataframe to use for 
    price crawling.

    Parameters:
        data_str: a row of pandas dataframe

    Returns:
        make (str): make of the car
        possible_models (lst): list of possible model names
            to try and crawl price from kbb
        year (int): year the car was made
    """
    make = data_str["make"]
    model_lst = data_str["model"].split()
    possible_models = [model_lst[0].lower(), "-".join(model_lst).lower(),]
    if len(model_lst) >= 2:
            possible_models +=  ["-".join(model_lst[:2]).lower()]
    
    year = int(data_str["year"])
    return make, possible_models, year


def calculate_savings(car_df, old_car_price):
    """
    Calculates the 5-year savings of the user, taking both
    fuel prices and car prices into account.
    
    Parameters:
        car_df (pd.DataFrame): dataframe of cars to be recommended
        old_car_price (float): price of the user's current car

    Returns:
        car_df (pd.DataFrame): dataframe of cars to be recommended
            with added five year saving column
    """
    car_df = car_df.astype({"year":"int32"})
    car_df.loc[:, "five_year_savings"] = 0

    car_df.loc[car_df.difference.notna(), "five_year_savings" ] = (
        car_df.loc[car_df.difference.notna(), "difference" ]
        + car_df.loc[car_df.difference.notna(), "yearly_savings"] * 5)

    car_df.loc[car_df.difference.isna(), "five_year_savings" ] = (
         car_df.loc[car_df.difference.isna(), "yearly_savings"] * 5)

    return car_df


def go():
    """
    Main program, takes users input (their current
    car and daily miles estimation) to compare their
    annual carbon emissions and spendings to that of
    other drivers. Program will then make recommendations
    of necessary milage reduction and potential new car
    purchases.
    """
    # Creates database if none already exists, skips this
    # computationally expensive processes otherwise.
    try:
        conn = sqlite3.connect('file:cscc.db?mode=rw', uri=True)
    except sqlite3.OperationalError:
        print('Local Database not found.\n'
              'Creating database...')
        conn = sqlite3.connect('cscc.db')
        build_db(conn)

    id_ = get_id(conn)
    use_miles = get_miles()

    emissions, gpm = get_emissions(conn, id_, use_miles)
    reduce_str = get_cut_recommendation(emissions, gpm)
    print(f'\nYearly CO2 emission: {emissions} grams.')
    print(reduce_str)
    input('Press any key to continue...\n')

    rank_order = rank_pref()
    rec_df = recommend_cars(conn, id_, use_miles, rank_order, gpm)
    if isinstance(rec_df, str):
        final_df = rec_df
    else:
        print('Calculating recommendations...')
        if emissions < AVG_EMISSION:
            print('Here are some cars that would help you further decrease '
                  'your carbon emission:')
        else:
            print('Here are some cars that would help you decrease your '
                  'carbon emission to the average:')
        df_with_savings = get_savings(conn, id_, use_miles, rec_df)
        df_with_prices, old_car_price = get_car_prices(df_with_savings)
        full_df = calculate_savings(df_with_prices, old_car_price)
    col = ['make', 'model', 'year', 'co2_emission', 'weekly_savings',
           'yearly_savings', 'price', 'difference', 'five_year_savings']
    final_df = full_df[col]
    final_df = final_df.sort_values('co2_emission')
    print(final_df.to_string(index=False, max_colwidth=20,
                             float_format=lambda x: f'{x:.2f}'))
    conn.close()


if __name__ == "__main__":
    go()