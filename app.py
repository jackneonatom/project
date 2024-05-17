from datetime import datetime, time, timedelta
from typing import Annotated, List, Optional
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, TypeAdapter, Field
import uuid
import motor.motor_asyncio
from dotenv import dotenv_values
from bson import ObjectId
from pymongo import ReturnDocument, MongoClient
import re
from datetime import timedelta
import requests

config = dotenv_values(".env")

client = motor.motor_asyncio.AsyncIOMotorClient(config["MONGO_URL"])
db = client.settings_data

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

origins=["http://127.0.0.1:8000","https://simple-smart-hub-client.netlify.app"]
# parse time function
regex = re.compile(r'((?P<hours>\d+?)h)?((?P<minutes>\d+?)m)?((?P<seconds>\d+?)s)?')


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PyObjectId = Annotated[str, BeforeValidator(str)]

# class to accept JSON
class Settings(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    user_temp: Optional[float] = None
    user_light: Optional[str] = None
    light_duration: Optional[str] = None
    light_time_off: Optional[str] = None

# class to return JSON
class returnSettings(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    user_temp: Optional[float] = None
    user_light: Optional[str] = None
    light_time_off: Optional[str] = None


def parse_time(time_str):
    parts = regex.match(time_str)
    if not parts:
        return
    parts = parts.groupdict()
    time_params = {}
    for name, param in parts.items():
        if param:
            time_params[name] = int(param)
    return timedelta(**time_params)

# get the sunset time in JAMAICA for that day
def get_sunset_time():
    URL = "https://api.sunrisesunset.io/json?lat=17.97787&lng=-76.77339" # this is for JAMAICA
    country_data = requests.get(url=URL).json()
    sunset = country_data["results"]["sunset"]

    # convert to 24 hr format
    user_sunset = datetime.strptime(sunset, '%I:%M:%S %p')

    return user_sunset.strftime('%H:%M:%S')
#  the

# put request
@app.put("/settings", status_code=200)
async def create_setting(settings: Settings):
    settings_check = await db["settings"].find().to_list(1)

    # determine whether user_light time is 'sunset' or given
    if settings.user_light == "sunset":
        user_light = datetime.strptime(get_sunset_time(), "%H:%M:%S")
    else:
        user_light = datetime.strptime(settings.user_light, "%H:%M:%S")
    
    # populate light time off
    duration = parse_time(settings.light_duration)
    settings.light_time_off = (user_light + duration).strftime("%H:%M:%S")

    # create setting if none
    if len(settings_check) == 0:        
        settings_info = settings.model_dump(exclude=["light_duration"])
        new_setting = await db["settings"].insert_one(settings_info)
        created_setting = await db["settings"].find_one({"_id": new_setting.inserted_id})

        return JSONResponse(status_code=201, content=returnSettings(**created_setting).model_dump())

    # update setting if entry exists
    else:            
        db["settings"].update_one(
            {"_id": settings_check[0]["_id"]},
            {"$set": settings.model_dump(exclude=["light_duration"])}
        )

        created_setting = await db["settings"].find_one({"_id": settings_check[0]["_id"]})

        return returnSettings(**created_setting)

# class for graph data collected from ESP
class graphData(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    temperature: Optional[float] = None
    presence: Optional[bool] = None
    datetime: Optional[str] = None

@app.get("/sensorData", status_code=200)
async def turn_on_components():
    data = await db["data"].find().to_list(999)

    # to use last entry in database
    last = len(data) - 1
    sensor_data = data[last]

    settings = await db["settings"].find().to_list(999)
    
    user_setting = settings[0]

    # if someone is in the room, should stuff turn on?
    if (sensor_data["presence"] == True):
        # if temperature is hotter or equal to slated temperature, turn on fan
        if (sensor_data["temperature"] >= user_setting["user_temp"]):
            fanState = True
        # else, turn it off
        else:
            fanState = False

        # if current time is equal to the slated turn on time, turn on light
        if (user_setting["user_light"] == sensor_data["datetime"]):
            lightState =  True
    
        else:
            on_check = await db["data"].find_one({"datetime": user_setting["user_light"]})
            off_check = await db["data"].find_one({"datetime": user_setting["light_time_off"]})
            
            # if current time is equal to the slated turn off time, turn off light
            if (user_setting["light_time_off"] == sensor_data["datetime"]):
                lightState =  False
            else:
                # if a previous current time matches with the setting OFF time, that means the light off time has passed and light should be off
                if(off_check != ""):
                    lightState = False
                # if off time has NOT passed, check if ON time has passed
                else:
                    # if a previous current time matches with the setting time, that means the light was on but hasn't turn off yet, therefore must be on
                    if(on_check != ""):
                        lightState = True
                    # otherwise, the turn on time hasn't come, light must be off
                    else:
                        lightState = False


        return_sensor_data = {
        "fan": fanState,
        "light": lightState
        }

    # if no one in room, everything off
    else:
        return_sensor_data = {
        "fan": False,
        "light": False
    }
    return return_sensor_data
@app.get("/sensorData", status_code=200)
async def turn_on_components():
    data = await db["data"].find().to_list(999)

    # to use last entry in database
    last = len(data) - 1
    if last < len(data):
     sensor_data = data[last]
    else:
    # Handle the case where the index is out of range, maybe return an error or handle it gracefully.
     sensor_data = None 

    settings = await db["settings"].find().to_list(999)
    
    user_setting = settings[0]

    # if someone is in the room, should stuff turn on?
    if (sensor_data["presence"] == True):
        # if temperature is hotter or equal to slated temperature, turn on fan
        if (sensor_data["temperature"] >= user_setting["user_temp"]):
            fanState = True
        # else, turn it off
        else:
            fanState = False

        # if current time is equal to the slated turn on time, turn on light
        if (user_setting["user_light"] == sensor_data["datetime"]):
            lightState =  True
    
        else:
            on_check = await db["data"].find_one({"datetime": user_setting["user_light"]})
            off_check = await db["data"].find_one({"datetime": user_setting["light_time_off"]})
            
            # if current time is equal to the slated turn off time, turn off light
            if (user_setting["light_time_off"] == sensor_data["datetime"]):
                lightState =  False
            else:
                # if a previous current time matches with the setting OFF time, that means the light off time has passed and light should be off
                if(off_check != ""):
                    lightState = False
                # if off time has NOT passed, check if ON time has passed
                else:
                    # if a previous current time matches with the setting time, that means the light was on but hasn't turn off yet, therefore must be on
                    if(on_check != ""):
                        lightState = True
                    # otherwise, the turn on time hasn't come, light must be off
                    else:
                        lightState = False


        return_sensor_data = {
        "fan": fanState,
        "light": lightState
        }

    # if no one in room, everything off
    else:
        return_sensor_data = {
        "fan": False,
        "light": False
    }
    return return_sensor_data
# get request to collect environmental data from ESP
@app.get("/graph")
async def get_data(size: int = None):
    data = await db["data"].find().to_list(size)
    return TypeAdapter(List[graphData]).validate_python(data)

# to post fake data to test get
@app.post("/graph", status_code=201)
async def create_data(data: graphData):
    new_entry = await db["data"].insert_one(data.model_dump())
    created_entry = await db["data"].find_one({"_id": new_entry.inserted_id})

    return graphData(**created_entry)