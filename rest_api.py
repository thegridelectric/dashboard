from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import dotenv
import pendulum
from sqlalchemy import create_engine, desc
from sqlalchemy.orm import sessionmaker
from config import Settings
from models import MessageSql

settings = Settings(_env_file=dotenv.find_dotenv())
valid_password = settings.thermostat_api_key.get_secret_value()
engine = create_engine(settings.db_url.get_secret_value())
Session = sessionmaker(bind=engine)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # allow_origins=["https://thegridelectric.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DataRequest(BaseModel):
    password: str

@app.post("/thermostats/{house_alias}")
async def get_latest_temperature(house_alias: str, request: DataRequest):

    if request.password != valid_password:
        raise HTTPException(status_code=403, detail="Unauthorized")

    session = Session()
    timezone = "America/New_York"
    start = pendulum.datetime(2024, 1, 1, 0, 0, tz=timezone)
    start_ms = int(start.timestamp() * 1000)

    last_message = session.query(MessageSql).filter(
        MessageSql.from_alias.like(f'%{house_alias}%'),
        MessageSql.message_persisted_ms >= start_ms
    ).order_by(desc(MessageSql.message_persisted_ms)).first()

    if not last_message:
        raise HTTPException(status_code=404, detail="No messages found.")

    temperature_data = []
    for channel in last_message.payload['ChannelReadingList']:
        if ('zone' in channel['ChannelName'] and 'gw' not in channel['ChannelName'] 
            and ('temp' in channel['ChannelName'] or 'set' in channel['ChannelName'])):
                temperature_data.append({
                    "zone": channel['ChannelName'],
                    "temperature": channel['ValueList'][-1] / 1000,
                    "time": last_message.message_persisted_ms
                })

    return temperature_data


@app.post("/hp_power/{house_alias}")
async def get_latest_temperature(house_alias: str, request: DataRequest, start_ms: int, end_ms: int):

    if request.password != valid_password:
        raise HTTPException(status_code=403, detail="Unauthorized")

    session = Session()

    messages = session.query(MessageSql).filter(
        MessageSql.from_alias.like(f'%{house_alias}%'),
        MessageSql.message_persisted_ms >= start_ms,
        MessageSql.message_persisted_ms <= end_ms,
    ).order_by(desc(MessageSql.message_persisted_ms)).all()

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found.")

    hp_odu_pwr = []
    hp_idu_pwr = []
    for message in messages:
        for channel in message.payload['ChannelReadingList']:
            if 'hp-odu-pwr' in channel['ChannelName']:
                hp_odu_pwr.extend(channel['ValueList'])            
            elif 'hp-idu-pwr' in channel['ChannelName']:
                hp_idu_pwr.extend(channel['ValueList'])

    hp_power_data = {
        'hp_odu_pwr': hp_odu_pwr,
        'hp_idu_pwr': hp_idu_pwr,
    }

    return hp_power_data


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
