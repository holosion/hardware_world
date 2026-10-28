"""Run the complete Flask HTML/CSS application with Waitress on Windows."""
import argparse
from waitress import serve
from main import app

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    serve(app, host=args.host, port=args.port)
