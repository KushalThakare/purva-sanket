"""Start the local application for physical ESP32 hardware or simulation."""
import argparse
import os
from pathlib import Path
import uvicorn

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', choices=['hardware', 'direct', 'http', 'mqtt', 'offline'], default='hardware')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    os.environ['PURVA_INPUT_MODE'] = args.input
    if args.input == 'mqtt' and not os.environ.get('PURVA_TOPIC'):
        topic_file = Path(__file__).parent / 'topic.txt'
        if not topic_file.exists():
            parser.error('First run: python configure_topic.py')
        os.environ['PURVA_TOPIC'] = topic_file.read_text().strip()
    print(f"Starting PURVA SANKET in [{args.input.upper()}] mode on {args.host}:{args.port}")
    uvicorn.run('backend.app:app', host=args.host, port=args.port)
