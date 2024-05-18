from datetime import datetime, time, timedelta
from typing import Annotated, List, Optional
from fastapi import Body, FastAPI, HTTPException, Response, status
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
import json
config = dotenv_values(".env")

client = motor.motor_asyncio.AsyncIOMotorClient(config["MONGO_URL"])
db = client.settings_data

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
format = "%Y-%m-%d %H:%M:%S %Z%z"
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

class sensorData(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    temperature: Optional[float] = None
    presence: Optional[bool] = None
    datetime: Optional[str] = None
  
# class to accept JSON
class Settings(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    user_temp: Optional[float] = None
    user_light: Optional[str] = None
    light_duration: Optional[str] = None
    light_time_off: Optional[str] = None
    

# class to return JSON
class updatedSettings(BaseModel):
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
def convert24(time):
    t = datetime.strptime(time, '%H:%M:%S')
    return t.strftime('%H:%M:%S')


def sunset_calculation():
    URL = "https://api.sunrisesunset.io/json"
    PARAMS = {"lat":"17.97787",
                "lng": "-76.77339"}
    r = requests.get(url=URL, params=PARAMS)
    response = r.json()
    sunset_time = response["results"]["sunset"]
    sunset_24 = convert24(sunset_time)
    return sunset_24

# put request
@app.put("/settings", status_code=200)
async def update_settings(settings_update: Settings = Body(...)):
    if settings_update.user_light == "sunset":
        user_light = datetime.strptime(sunset_calculation(), "%H:%M:%S")
    else:
        user_light = datetime.strptime(settings_update.user_light, "%H:%M:%S")

    duration = parse_time(settings_update.light_duration)
    settings_update.light_time_off = (user_light + duration).strftime("%H:%M:%S")
    

    all_settings = await db["settings"].find().to_list(999)
    if len(all_settings)==1:
        db["settings"].update_one({"_id":all_settings[0]["_id"]},{"$set":settings_update.model_dump(exclude = ["light_duration"])})
        updated_settings = await db["settings"].find_one({"_id": all_settings[0]["_id"]})
        return updatedSettings(**updated_settings)
    
    else:
        new_settings = await db["settings"].insert_one(settings_update.model_dump(exclude = ["light_duration"]))
        created_settings = await db["settings"].find_one({"_id": new_settings.inserted_id})
        final = (updatedSettings(**created_settings)).model_dump()
        # raise HTTPException(status_code=201)
        return JSONResponse(status_code=201, content=final)

# class for graph data collected from ESP
class graphData(BaseModel):
    id: Optional[PyObjectId] = Field(alias = "_id", default = None)
    temperature: Optional[float] = None
    presence: Optional[bool] = None
    datetime: Optional[str] = None

@app.post("/sensorData",status_code=201)
async def createSensorData(sensor_data:sensorData):
    entry_time = datetime.now().strftime("%H:%M:%S")
    sensor_data_ = sensor_data.model_dump()
    sensor_data_["datetime"] = entry_time
    new_data = await db["sensorData"].insert_one(sensor_data_)
    created_data = await db["sensorData"].find_one({"_id": new_data.inserted_id})
    return sensorData(**created_data)

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
        if (user_setting["user_light"] == sensor_data["datetime"]):
            lightState =  True
    
        else:
            on_check = await db["sensorData"].find_one({"datetime": user_setting["user_light"]})
            off_check = await db["sensorData"].find_one({"datetime": user_setting["light_time_off"]})
            if (user_setting["light_time_off"] == sensor_data["datetime"]):
                lightState =  False
            else:
                # if a previous current time matches with the setting OFF time, that means the light off time has passed and light should be off
                if(off_check != ""):
                    lightState = False
                # if off time has NOT passed, check if ON time has passed
                else:
                    if(on_check != ""):
                        lightState = True
                    else:
                        lightState = False


        return_sensor_data = {
        "fan": fanState,
        "light": lightState
        }

    # if no one in room
    else:
        return_sensor_data = {
        "fan": False,
        "light": False
    }
    return return_sensor_data
# get request to collect environmental data from ESP
@app.get("/fan", status_code=200)
async def fan_control():
    sensorData = await db["sensorData"].find().to_list(999)
    num = len(sensorData) - 1
    sensors = sensorData[num]

    all_settings = await db["settings"].find().to_list(999)
    user_pref = all_settings[0]

    if (sensors["presence"] == True):

        if (sensors["temperature"] >= user_pref["user_temp"]):
            fanState = True
        else:
            fanState = False
    else:
        fanState = False
    
    componentState = {
        "fan": fanState
    }

    return componentState

@app.get("/light", status_code=200)
async def light_control():
    sensorData = await db["sensorData"].find().to_list(999)
    num = len(sensorData) - 1
    sensors = sensorData[num]

    all_settings = await db["settings"].find().to_list(999)
    user_pref = all_settings[0]

    set_start_time = datetime.strptime(user_pref["user_light"], '%H:%M:%S')
    set_end_time = datetime.strptime(user_pref["light_time_off"], '%H:%M:%S')
    current_time = datetime.strptime(sensors["datetime"], '%H:%M:%S')

    if (sensors["presence"] == True):
        if ((current_time>set_start_time) & (current_time<set_end_time)):
                lightState = True
        else:
                lightState = False
    else:
        lightState = False
    
    componentState = {
        "light": lightState
    }

    return componentState
@app.get("/graph", status_code=200)
async def get_data(size: int = None):
    data = await db["sensorData"].find().to_list(size)
    return TypeAdapter(List[sensorData]).validate_python(data)

