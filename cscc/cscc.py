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

import questionary as q
from questionary import ValidationError
from questionary import Style

URL = "https://www.fueleconomy.gov/feg/epadata/vehicles.csv"

DATA_COLS = ['id', 'make', 'model', 'year', 'trany', 'drive', 'cylinders',
             'VClass', 'pv2', 'pv4', 'hpv', 'lv2', 'lv4', 'hlv', 'fuelCost08',
             'fuelCostA08', 'fuelType', 'co2TailpipeGpm', 'co2TailpipeAGpm']

WHERE_CMD = "WHERE make = ? AND model = ? AND year = ?"

AVG_EMISSION = 4600000
AVG_CO2 = [89038.5]   #g/week
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


# Used as questionary parameters to reject user input
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

def get_miles():
    """
    Asks user for estimation of their current weekly miles.
    Used to calculate their emission.

    Returns:
        dict: Pairs user's miles (str) with its value (float)
    """
    use_miles = q.text('Estimation for weekly miles driven?\n   ',
                       validate=lambda text: txt_validator(text),
                       style=Style(S_CONFIG), qmark='\n⯁ ').ask()
    return {'use_miles': float(use_miles)}

def rank_pref():
    """
    Ranks vehicle attributes that user cares most about from their
    current car. Uses this information to more accurately recommend
    a new vehicle.

    Returns:
        dict: Pairs rank (int) with category (str)
    """
    CHOICES = ['Make', 'Year', 'Transmission', 'Vehicle Class', 'Fuel Type',
               'Passenger capacity', 'Luggage Capacity', 'Stop Ranking']
    q.print('We will now ask you to rank which attributes you like most '
            'about your current vehicle.\nThese choices will be taken into '
            'consideration for car recommendation.\nYou may rank until you '
            "feel you have no more preferences or until you've exhausted all "
            'options.', style=S_CONFIG[1][1])

    i = 1
    pref = ''
    ranking_dict = dict()
    while len(CHOICES) > 2:
        pref = q.select('Choose preference: ', choices=CHOICES,
                        style=Style(S_CONFIG), qmark='\n' + str(i)).ask()
        if pref == 'Stop Ranking':
            break
        CHOICES.remove(pref)
        ranking_dict[i] = pref
        i += 1
    if len(CHOICES) == 2:
        ranking_dict[i] = CHOICES[0]
    return ranking_dict


def get_emissions(conn, id_, input_dict):
    """
    """
    c = conn.cursor()
    s = "SELECT co2TailpipeGpm, co2TailpipeAGpm FROM vehicles WHERE id = ?"
    r = c.execute(s, (id_,))
    rv = r.fetchall()
    c.close()

    use = input_dict["use_miles"]

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
    r = c.execute(s1, [str(car_id)])
    rv = r.fetchall()
    db.close

    fuel1_cost, fuel2_cost = rv[0]

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
            AS co2_emission, year, trany FROM vehicles WHERE co2_emission <= ?"
    
    alt_s = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, \
             year, trany FROM vehicles" #to be potentially used later 
            
    a = c.execute(s1, AVG_CO2)

    df = pd.DataFrame(a.fetchall(), columns=["id", "make","model", "pv2", \
        "pv4", "hpv", "lv2", "lv4", "hlv", "fuelType", "VClass", \
        "co2_emission", "year", "trany"])

    s2 = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, year, trany FROM vehicles WHERE id = ?"

    old_car = c.execute(s2, [str(id)])
    car_id, car_make, car_model, car_pv2, car_pv4, car_hpv, \
        car_lv2, car_lv4, car_hlv, car_fuelType, car_VClass, year, trany = old_car.fetchall()[0]

    car_lv = max(car_lv4, car_hlv, car_lv2) #taking the max since some will have 0 as entries
    car_pv = max(car_pv2, car_pv4, car_hpv)

    match_dict = {"make":car_make, "VClass":car_VClass, \
        "fuelType":car_fuelType, "year": year, "luggage_volume": car_lv, \
        "passenger_volume": car_pv, "trany": trany}

    car_dict = {"id":car_id, "make":car_make,"model": car_model, \
        "pv2": car_pv2, "pv4":car_pv4,"hpv":car_hpv,\
        "lv2":car_lv2, "lv4":car_lv4, "hlv":car_hlv, \
        "fuelType":car_fuelType, "VClass":car_VClass, "year":year, "trany": trany}

    df = df.append(car_dict, ignore_index=True) #important for the price function for this to be the LAST row
    
    for i in range(1, len(ranking_dict)+1):
        of_interest = ranking_dict[i]
        if of_interest  in ["make", "VClass", "fuelType"]:
            new_df = df[df[of_interest] == match_dict[of_interest]]
        elif of_interest == "year":
            new_df = df[(df[of_interest] >= match_dict[of_interest]
             - 5) & (df[of_interest] <= match_dict[of_interest] + 5)]
        elif of_interest == "trany":
            m = df["trany"].str.split(" ", expand=True).iloc[:, 0]
            new_d = pd.concat([df, m], axis=1)
            new_df = new_d[new_d.iloc[:, -1] == match_dict[of_interest].split()[0]]
            new_df = new_df.drop(new_df.columns[-1], axis=1)
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
    
    if len(df) > 20:  #dropping the original car, sampling, adding it again
        df = df.drop(index=df[df["id"] == input_dict["id"]].index)
        df = df.sample(n=20, random_state=1)
        df = df.append(car_dict, ignore_index=True)

    return df


def get_savings(db, input_dict, df, id):
    '''
    Given a df from recommend_cars(), and the user's own car's id,
    calculate the fuel costs and savings and add them to the df returned.
    '''
    new_df = pd.DataFrame()
    miles = input_dict["use_miles"]

    s = "SELECT id, make, model, pv2, pv4, hpv, lv2, lv4, hlv, fuelType, VClass, year, trany FROM vehicles WHERE id = ?"
    old_weekly_cost = get_fuel_price(db, id, miles)
    old_yearly_cost = old_weekly_cost * 52

    for _, row in df.iterrows():
        car_id = row['id']
        weekly_cost = get_fuel_price(db, car_id, miles)
        yearly_cost = weekly_cost * 52
        weekly_savings = old_weekly_cost - weekly_cost
        yearly_savings = old_yearly_cost - yearly_cost
        new_row = row.copy()
        new_row['weekly_cost'] = weekly_cost
        new_row['yearly_cost'] = yearly_cost
        new_row['weekly_savings'] = weekly_savings
        new_row['yearly_savings'] = yearly_savings
        new_df = new_df.append(new_row)

    return new_df


def get_volume(cursor, string, id, type_):
    '''
    Get luggage or passenger volume of the input car if it is missing
    '''
    if type_ == "lv":
        lst = ["lv2", "lv4", "hlv"]
    else:
        lst = ["pv2", "pv4", "hpv"]

    b = cursor.execute(string)
    new_df = pd.DataFrame(b.fetchall(), columns = ["id", "make", \
        "model", "pv2", "pv4", "hpv", "lv2", "lv4", "hlv", \
        "fuelType", "VClass", "year", "trany"])
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
    year = int(data_str["year"])

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
    car_df["price"] = "N/A"

    pm = urllib3.PoolManager(
       cert_reqs='CERT_REQUIRED',
       ca_certs=certifi.where())
    
    old_car_price = None
    car_df = car_df.reset_index()

    for i, row in car_df.iterrows():
        make, possible_models, year = get_info_for_price(row)
        if year < 1992 and i != len(car_df) - 1:
            continue
        for j, model in enumerate(possible_models):
            myurl = "https://www.kbb.com/{}/{}/{}/".format(make, model, year)
            html = pm.urlopen(url=myurl, method="GET").data
            soup = bs4.BeautifulSoup(html, features="html.parser")
            title = soup.find_all("title")[0].text
            if ("Find Your Perfect Car" not in title) and ("Kelley Blue Book | Error" not in title):
                break
        if ("Find Your Perfect Car" in title) or ("Kelley Blue Book | Error" in title) or (str(year) not in title):
            continue
        price_text = soup.find_all("script", attrs={"data-rh":"true"})[-1].text
        m =  re.findall('"price":"([0-9]+)"', price_text)[0]
        if i == len(car_df) - 1:
            old_car_price =int(m) 
        car_df.loc[i, "price"] = int(m) 
    
    old_car_price = q.text('No associated price could be found for your car.\n'
                           'What do you believe your car is worth?',
                           validate=lambda text: txt_validator(text),
                           style=Style(S_CONFIG + [('qmark', 'fg:#CF5050')]),
                           qmark='\n❗').skip_if(old_car_price is not None).ask()
    car_df["difference"] = old_car_price - car_df.price[car_df.price != "N/A"]

    return car_df, old_car_price

def calculate_savings(car_df, old_car_price):

    car_df["five_year_savings"] = 0
    car_df.five_year_savings[car_df.difference.notna()] = car_df.difference[car_df.difference.notna()] + \
            car_df.yearly_savings[car_df.difference.notna()] * 5
    
    car_df.five_year_savings[car_df.difference.isna()] = car_df.yearly_savings[car_df.difference.isna()] * 5

    return car_df


def go():
    """
    Main program, takes users input (their current
    car and daily miles estimation) to compare their
    annual carbon emissions and spendings to that of
    other drivers. Program will then make recommendations
    of necessary milage reduction, or potential new car
    purchases/(public transportation use).
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
    input_dict = get_miles()

    # Calculate and print the emissions for debugging
    emissions = get_emissions(conn, id_, input_dict)
    print('Yearly CO2 emission: ' + str(emissions) + ' grams.')
    input('Press any key to continue...')

    ranking_dict = rank_pref()
    print('Debug ranking: ')
    print(ranking_dict)

    conn.close()

if __name__ == "__main__":
    go()
