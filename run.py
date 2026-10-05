"""Start the local prototype with synthetic replay or Wokwi/MQTT inputs."""
import argparse
import os
from pathlib import Path
import uvicorn

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',choices=['offline','mqtt'],default='offline')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    os.environ['PURVA_INPUT_MODE']=args.input
    if args.input=='mqtt' and not os.environ.get('PURVA_TOPIC'):
        topic_file=Path(__file__).parent/'topic.txt'
        if not topic_file.exists():
            parser.error('First run: python configure_topic.py')
        os.environ['PURVA_TOPIC']=topic_file.read_text().strip()
    uvicorn.run('backend.app:app',host='127.0.0.1',port=args.port)
