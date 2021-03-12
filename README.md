# CS122-Project (CSCC)

## HOW TO RUN
 One must first install questionary by running `pip install questionary` in your terminal of choice.
 Once that has been done, simply run cscc.py from inside its directory either through the command line using `python3 cscc.py` or in ipython with `run cscc.py`.
 (Terminal with black background is prefered for styling purposes)

### Key
If the final car recommendation output from the program seems unclear here is a table with descriptions for each header.
Col               | Desc
------------------|-----------------------------
make              | brand of the recommended car
model             | model of the recommended car
year              | manufacturing year of the recommended car
co2_emission      | recommended car's weekly CO2 emission based on the user's weekly miles driven
weekly_savings    | how much the user will save on fuel costs with the new recommended car in a week (in dollars)
yearly_savings    | how much the user will save on fuel costs with the new recommended car in a year (in dollars)
price             | the price of the recommended car
difference        | the price difference between the recommended car and the user's current car
five_year_savings | how much the user will save in 5 years overall, considering both fuel cost savings and the price difference between the two cars

## Members
Efe Doğruöz  
Ebru Ermiş  
Mey Abdullahoğlu  
Kevin Ramirez

## Project Desc. and Goals
Transportation is one of the sectors that contributes the most to climate change.
Use of personal vehicles as opposed to public transportation or biking, as well as car choice, cause increased greenhouse gas emissions and exasperate global warming.
Toning down personal car use is an important step the average person can take against global warming.  
We want to build a software system that, given your car model and information on how much you drive, gives you an estimate of your carbon emission due to personal vehicle usage and how much you should decrease your car usage based on a comparison with the average person’s carbon emission due to car usage in the U.S. Moreover, the system will also compile a list of recommendations for new potential cars using user's preferences and display their saving over some timeframes given that they switched.

## Data Sources
* [Fuel Economy](https://www.fueleconomy.gov/feg/ws) is a US government website that gives information about the greenhouse gas emissions of car models starting from 1984.
* [Kelley Blue Book](https://www.kbb.com/) site used to evaluate car prices. Older cars may not have pricing information.
* [EPA](https://www.epa.gov/greenvehicles/fast-facts-transportation-greenhouse-gas-emissions) is a federal website that gives information about greenhouse gas emissions in the US by sector (and car type within transportation) and year.

## Pending Timeline
Date   | Task
------ | ----
Feb 7  | &#9745; Write code to get vehicle id from user's limited information
Feb 14 | &#9745; Write code that takes in model and use, and returns emissions data
Feb 21 | &#9745; Write code to rank user's priorities in a new car
Feb 28 | &#9745; Write code that compares and subsequently recommends other cars
Mar 7  | &#9745; Look up new car prices and translate the output to a user interface
