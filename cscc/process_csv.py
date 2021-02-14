import pandas as pd

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