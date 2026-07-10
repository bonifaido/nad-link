NAD Link for Raspberry Pi
=====

Thanks to Morten Hustveit who [did all the work](http://www.ping.uio.no/~mortehu/nadlink/).

This works well on my C350 amp – a quick bodge connecting a GPIO pin and ground pin to an RCA connector was all that was needed. It seems happy enough with 3.3v instead of the specified 5.

Specify the correct pin in the script.

I like to do the following in my `.zshrc`:

````
alias nad='python /opt/nad-link/nad-link.py'
````

And on my other computers:
````
alias nad='ssh pi -t python /opt/nad-link/nad-link.py'
````
(The `-t` tells ssh to imitate a terminal so the SIGTERM from pressing `^C` is forwarded. This is helpful in order to kill the command properly, and thus stop volume changes at the intended moment before waking up the entire town.)

Then it's just
````
$ nad on
$ nad off
$ nad up
$ nad down
````
etc. etc.


Daemon
-----

I've now included an example of a very simple daemon which listens for volume control events from my Bluetooth remote (or therefore, presumably, any keyboard's volume keys) and launches the script to do the relevant volumizing.


Home Assistant
-----

For Home Assistant, the simplest approach is to keep `nad-link.py` as the timing-critical transmitter and run a separate long-lived HTTP wrapper that invokes it on demand.

Start the daemon on the Pi:

````
$ python3 /opt/nad-link/nad-link-http.py --host 0.0.0.0 --port 5384
````

Health check:

````
$ curl http://pi-zero:5384/health
````

Send a command:

````
$ curl -X POST http://pi-zero:5384/command/power
$ curl -X POST http://pi-zero:5384/command/cd
$ curl -X POST http://pi-zero:5384/command/up
$ curl -X POST http://pi-zero:5384/command/code \
	-H 'Content-Type: application/json' \
	-d '{"hexcode":"e13e01fe"}'
````

The `up` and `down` commands are treated as hold commands by the daemon and default to a short 200ms press. You can override that per request:

````
$ curl -X POST http://pi-zero:5384/command/up \
	-H 'Content-Type: application/json' \
	-d '{"hold_ms":500}'
````

There is also a sample systemd unit in `nad-link-http.service`.

In Home Assistant, define a few REST commands in `configuration.yaml`:

````yaml
rest_command:
	nad_power:
		url: "http://pi-zero:5384/command/power"
		method: POST

	nad_cd:
		url: "http://pi-zero:5384/command/cd"
		method: POST

	nad_volume_up:
		url: "http://pi-zero:5384/command/up"
		method: POST
		content_type: "application/json"
		payload: '{"hold_ms":250}'

	nad_volume_down:
		url: "http://pi-zero:5384/command/down"
		method: POST
		content_type: "application/json"
		payload: '{"hold_ms":250}'

	nad_mute:
		url: "http://pi-zero:5384/command/mute"
		method: POST
````

You can then expose those as buttons, scripts, or dashboard actions in the Home Assistant UI.


Futility
--------

It's been pointed out that I could have just used `lirc` and saved a lot of effort. This is most likely a correct observation, but by doing that I wouldn't have learned anything, and would have probably just spent time getting annoyed by boring problems configuring it to use GPIO. Too much like work! So no complaining from me.


Config
-----

Just change the config at the top of the script. Alias remote codes however you like.

~~I'll point you again at [Morten Hustveit's page](http://www.ping.uio.no/~mortehu/nadlink/).~~ The page is gone, apparently forever.

I've [tried to convert](https://github.com/tsprlng/nad-link/issues/4) the Crestron codes NAD provide and included them here in [the remote-codes directory](./remote-codes). Some of them have a trailing '3' for some reason which makes them longer than the normal 4 bytes. I don't have a NAD CD player so have no idea what's going on or what is correct.

For different equipment just extract the right remote codes (it's easy to enter hex into YAML). Be aware that my script expects them in normal left-to-right reading endianness (whichever that is) so just take the binary and hexify it.
