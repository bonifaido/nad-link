#!/usr/bin/env python3

import argparse
import json
import os
import signal
import subprocess
import sys
import time

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse


DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 5384
DEFAULT_HOLD_MS = 200
HOLD_COMMANDS = {'up', 'down'}


def parseArgs():
  parser = argparse.ArgumentParser(description='HTTP daemon for nad-link.py')
  parser.add_argument('--host', default=DEFAULT_HOST, help='Address to bind to')
  parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to listen on')
  parser.add_argument(
      '--command-script',
      default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nad-link.py'),
      help='Path to the nad-link transmitter script'
  )
  parser.add_argument(
      '--default-hold-ms',
      type=int,
      default=DEFAULT_HOLD_MS,
      help='Default hold duration for hold-style commands such as up/down'
  )
  return parser.parse_args()


def jsonResponse(handler, status, payload):
  body = json.dumps(payload, sort_keys=True).encode('utf-8')
  handler.send_response(status)
  handler.send_header('Content-Type', 'application/json')
  handler.send_header('Content-Length', str(len(body)))
  handler.end_headers()
  handler.wfile.write(body)


def readJsonBody(handler):
  contentLength = int(handler.headers.get('Content-Length', '0'))
  if contentLength == 0:
    return {}

  rawBody = handler.rfile.read(contentLength)
  if not rawBody:
    return {}

  try:
    return json.loads(rawBody.decode('utf-8'))
  except (UnicodeDecodeError, json.JSONDecodeError) as ex:
    raise ValueError('Request body must be valid JSON') from ex


def buildCommand(scriptPath, commandName, payload):
  command = [sys.executable, scriptPath, commandName]

  if commandName == 'code':
    hexcode = payload.get('hexcode') or payload.get('code')
    if not hexcode:
      raise ValueError("The 'code' command requires a 'hexcode' field")
    command.append(str(hexcode))

  return command


def runCommand(scriptPath, commandName, payload, defaultHoldMs):
  command = buildCommand(scriptPath, commandName, payload)

  if commandName in HOLD_COMMANDS:
    holdMs = payload.get('hold_ms', defaultHoldMs)
    try:
      holdMs = int(holdMs)
    except (TypeError, ValueError) as ex:
      raise ValueError("'hold_ms' must be an integer") from ex

    if holdMs < 0:
      raise ValueError("'hold_ms' must be non-negative")

    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
      time.sleep(holdMs / 1000.0)
      if process.poll() is None:
        process.send_signal(signal.SIGINT)
      stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
      process.kill()
      stdout, stderr = process.communicate()

    return {
        'command': commandName,
        'hold_ms': holdMs,
        'returncode': process.returncode,
        'stderr': stderr.strip(),
        'stdout': stdout.strip(),
    }

  completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
  return {
      'command': commandName,
      'returncode': completed.returncode,
      'stderr': completed.stderr.strip(),
      'stdout': completed.stdout.strip(),
  }


class NADLinkHTTPHandler(BaseHTTPRequestHandler):
  server_version = 'NADLinkHTTP/1.0'

  def do_GET(self):
    parsed = urlparse(self.path)
    if parsed.path == '/health':
      jsonResponse(self, 200, {'status': 'ok'})
      return

    jsonResponse(self, 404, {'error': 'not found'})

  def do_POST(self):
    parsed = urlparse(self.path)
    if not parsed.path.startswith('/command/'):
      jsonResponse(self, 404, {'error': 'not found'})
      return

    commandName = unquote(parsed.path[len('/command/'):]).strip()
    if not commandName or '/' in commandName:
      jsonResponse(self, 400, {'error': 'invalid command path'})
      return

    try:
      payload = readJsonBody(self)
      result = runCommand(
          self.server.commandScript,
          commandName,
          payload,
          self.server.defaultHoldMs,
      )
    except ValueError as ex:
      jsonResponse(self, 400, {'error': str(ex)})
      return
    except subprocess.TimeoutExpired:
      jsonResponse(self, 504, {'error': 'transmitter command timed out'})
      return
    except OSError as ex:
      jsonResponse(self, 500, {'error': str(ex)})
      return

    if result['returncode'] != 0:
      jsonResponse(self, 502, result)
      return

    jsonResponse(self, 200, result)

  def log_message(self, format, *args):
    sys.stderr.write('%s - - [%s] %s\n' % (self.address_string(), self.log_date_time_string(), format % args))


def main():
  args = parseArgs()
  server = ThreadingHTTPServer((args.host, args.port), NADLinkHTTPHandler)
  server.commandScript = args.command_script
  server.defaultHoldMs = args.default_hold_ms
  print('nad-link HTTP daemon listening on {}:{} using {}'.format(args.host, args.port, args.command_script))
  server.serve_forever()


if __name__ == '__main__':
  main()