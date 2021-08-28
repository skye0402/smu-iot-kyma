# Retrieve the weather forecast from openweather.com and store it in REDIS
# This application runs in a pod on Kyma
# ------------------------------------------------------------------------
# Developed for SMU Challenge 2021
#
# What is the meaning of precipitation in mm? (Rainfall)
#   Light rain — when the precipitation rate is < 2.5 mm per hour
#   Moderate rain — when the precipitation rate is between 2.5 mm – 7.6 mm or 10 mm per hour
#   Heavy rain — when the precipitation rate is > 7.6 mm per hour, or between 10 mm and 50 mm per hour
#   Violent rain — when the precipitation rate is > 50 mm per hour

import time
from datetime import datetime
from datetime import date as dt_date
import dateutil.parser
import configparser
import requests
from requests.auth import HTTPBasicAuth
import json
from json import JSONEncoder
import redis


# Helper function for K8S deployment
def endless_loop(msg):
    print(msg + " Entering endless loop. Check and redo deployment?")
    while True:
        pass

# Get configuration
config = configparser.ConfigParser(inline_comment_prefixes="#")
config.read(['./config/weather.cfg'])
if not config.has_section("openweather"):
    endless_loop("Config: openweather section missing.")
if not config.has_section("timing"):
    endless_loop("Config: timing section missing.")    
if not config.has_section("redis"):
    endless_loop("Config: Redis section missing.")
if not config.has_section("irrigation"):
    endless_loop("Config: irrigation section missing.")   
if not config.has_section("sapiot"):
    endless_loop("Config: sapiot section missing.")       
# -------------- Parameters ------------------>>>
relOpenWeatherUrl = config.get("openweather","url")
locLat = config.get("openweather","lat")
locLon = config.get("openweather","lon")
unitSystem = config.get("openweather","units")
language = config.get("openweather","lang")
apiKey =  config.get("openweather","apiid")
excludeInfo = config.get("openweather","exclude")

runtimeOfProgram = int(config.get("timing","runtimeOfProgram"))
retrievalInterval = int(config.get("timing", "pauseInSeconds"))
weatherTimeout = int(config.get("timing", "weatherTimeout"))

redisHost = config.get("redis", "redisHost")
redisPort = int(config.get("redis", "redisPort"))
redisPassword = config.get("redis", "redisPassword")
redisDb = int(config.get("redis", "redisDb"))

rainfallMin = int(config.get("irrigation", "rainfallMin"))
rainfallKey = config.get("irrigation", "rainfallKey")
irrigationDuration = int(config.get("irrigation", "irrigationDuration"))
irrigationDuration

commandUrl = config.get("sapiot", "commandUrl")
iotUser = config.get("sapiot", "iotUser")
iotPassword = config.get("sapiot", "iotPassword").replace("'","")
iotgetDataEvent = config.get("sapiot", "iotgetDataEvent")
# -------------- Parameters ------------------<<<

# Connect to Redis DB
r = redis.Redis(host=redisHost, port=redisPort, db=redisDb, password=redisPassword, socket_timeout=None, decode_responses=True)

def getEventsFromRedis():
    events = r.hgetall("things")
    eventList = { }
    i = 1
    for e in events:
        eventList[i] = {}
        eventList[i]['thingId']=e
        eventList[i]['timestamp']=events[e]
        i = i + 1
    return eventList

# subclass JSONEncoder
class DateTimeEncoder(JSONEncoder):
        #Override the default method
        def default(self, obj):
            if isinstance(obj, (dt_date, datetime)):
                return obj.isoformat()

# custom Decoder for datetime
def DecodeDateTime(dateDict):
    if 'waterts' in dateDict:
        tsStr = dateDict['waterts']
        return dateutil.parser.parse(tsStr)

# Gets age of timestamp in minutes
def getAgeOfEvent(timeStamp):
    timeDiff = datetime.now() - timeStamp
    return divmod(timeDiff.total_seconds() , 60)[0]

# Get thing from Redis
def getThingFromRedis(thingId):
    return r.hgetall(thingId)

# Raise NATS event to request Thing data
def raiseNeedThingEvent(thingId):
    callUrl = "http://eventing-event-publisher-proxy.kyma-system/publish"
    # callUrl = "https://gunter-ext-event.c-0db7077.kyma.shoot.live.k8s-hana.ondemand.com" (for local testing)
    headers = { "Content-Type" : "application/cloudevents+json" }
    body = '{ "source": "kyma", "specversion": "1.0", "eventtypeversion": "v1", "data": {"thingId": "' + thingId + '"}, "datacontenttype": "application/json", "id": "759815c3-b142-48f2-bf18-c6502dc0998s", "type": "'+ iotgetDataEvent + '" }'
    response = requests.post(callUrl, headers=headers, data=body)
    data = json.loads(response.text)
    print("Raised event to obtain thing data with response " + str(response.status_code) + ".")

# get weather (ideally cached)
def getCachedWeather():
    # Create request url
    openWeatherUrl = "https://" + relOpenWeatherUrl + "?lat=" + locLat + "&lon=" + locLon + "&exclude=" + excludeInfo + "&units=" + unitSystem + "&lang=" + language + "&appid=" + apiKey
    
    # Check if in Redis Cache
    rainfall = -1.0
    rainfallStr = r.get(rainfallKey)
    if rainfallStr == None:
        # Retrieve from openWeather
        response = requests.get(openWeatherUrl)
        data = json.loads(response.text)
        print("No cached weather forecast available. Called openWeather with response " + str(response.status_code) + ".")
        if response.status_code == 200:
            today = data['daily'][1]
            rainfall = today['rain']
            print("Forecasted rainfall: " + str(rainfall) + "mm.")
            r.setex(rainfallKey, rainfallMin * 60, rainfall)
    else: 
        rainfall = float(rainfallStr)
        print("Cached forecasted rainfall: " + str(rainfall) + "mm.")
    return rainfall  

# Send watering command
def sendWateringCommand(thing, cmd):
    callUrl = commandUrl + thing['deviceId'] + '/commands'
    headers = { "Content-Type": "application/json"}
    body = '{ "capabilityId": "' + thing["commandCapabilityId"] + '", "command": { "irrigationStatus": "' + cmd + '"}, "sensorId": "' + thing["sensorId"] + '" }'
    response = requests.post(callUrl,headers=headers, data=body, auth=HTTPBasicAuth(iotUser, iotPassword))
    data = json.loads(response.text)
    print("Sent irrigation command '" + cmd + "' with response: " + str(response.status_code) + " / " + data['message'])


# Checks if the watering is needed and if it's running whether it needs to be switched off
def handleIrrigation(thing, thingData, rainfall):
    irrigationKey = 'irrigation-' + thing['thingId'] 
    timestampStr = r.get(irrigationKey)
    if timestampStr == None: #No watering command was sent for this thing
        if rainfall < rainfallMin:
            print("Forecasted rainfall is "+ str(rainfall) + "mm and therefore below defined minimum of " + str(rainfallMin) + "mm. Turning on irrigation system.")
            sendWateringCommand(thingData, "start")
            startTime = { "waterts": datetime.now() }
            jsonTimeStamp = DateTimeEncoder().encode(startTime)
            r.set(irrigationKey, jsonTimeStamp) 
        else:
            print("Forecasted rainfall is "+ str(rainfall) + "mm and therefore above defined minimum of " + str(rainfallMin) + "mm. No watering needed.")
    else: #Needs check if it must be turned off
        then = DecodeDateTime(json.loads(timestampStr))
        minutes = getAgeOfEvent(then)
        if minutes >= irrigationDuration:
            #turn off, the time has been reached, and clean up the keys
            sendWateringCommand(thingData, "stop")
            print("Watering stopped, watering time of " + str(minutes) + "min meets irrigation setting of " + str(irrigationDuration) + "min. Redis keys deleted. Timestamp was: " + thing['timestamp'] + ".")
            r.delete(irrigationKey) #Delete watering marker
            r.hdel("things", thing['thingId'] ) #Delete low moisture event            

# The main program
def main():    
    print("******************** Starting up irrigation controller component ********************")
    loopCondition = True
    then = datetime.now()

    # Start sending data to cloud
    while loopCondition:
        if runtimeOfProgram > 0: # Check if program should halt
            now = datetime.now()
            durationMins = divmod((now-then).total_seconds(), 60)[0]
            if durationMins >= runtimeOfProgram:
                loopCondition = False
        
        # Check if there is workload (new event)
        workload = getEventsFromRedis()

        if workload != {}:
            # Check if thing(s) exist in Redis
            for thingNo in workload:
                thing = workload[thingNo]
                currentThing = getThingFromRedis(thing['thingId'])
                if currentThing == {}:
                    raiseNeedThingEvent(thing['thingId'])
                    break
                # In case of workload and available thing data check for cached weather
                rainfall = getCachedWeather()

                # Now check if irrigation command must be sent (switch on/off)
                handleIrrigation(thing, currentThing, rainfall)    

        time.sleep(retrievalInterval) # Wait until next call
        print("Next loop.")
    endless_loop("Program has reached the maximum set run time. Entering endless loop. Delete pod to restart or adjust configuration file.")

if __name__ == "__main__":
    main()