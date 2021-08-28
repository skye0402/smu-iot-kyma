# Just a bit of testing on Redis
# 
import redis
import time

r = redis.Redis(host="localhost", port = 6379, db=0, password="kPppOZp2hC", socket_timeout=None, decode_responses=True) # decode responses converts from byte to string

#data = {"capID": "123", "devID": "d100", "sensID": "s200"}
#r.hset("thingIDxyz", mapping=data)
#r.delete("1F24CC00EEE740B49FE8DED942AA6AF5")
#r.delete("things")
print(r.hgetall("1F24CC00EEE740B49FE8DED942AA6AF5")) #from thing data
print(r.hgetall("things")) # from low moisture
#r.hdel("things","1F24CC00EEE740B49FE8DED942AA6AF5")



# thingData = {"2F24CC00EEE740B49FE8DED942AA6AF5": "1245"}
# r.hset("things", mapping=thingData)
# thingData = {"4F24CC00EEE740B49FE8DED942AA6AF6": "1246"}  
# r.hset("things", mapping=thingData)

# for thingId in r.hscan_iter("things"):
#     print("Thing ID: " + str(thingId[0]) + " Timestamp: " + str(thingId[1]))



# r.set('bye', "In 5 seconds, I'll self-delete", ex=5)
# print(r.get("bye"))
# time.sleep(5)
# print(r.get("bye"))
# print(r.get("Bahamas"))
# print(r.get("Croatia"))

# r.delete("Croatia")

# print(r.get("Croatia"))