### WEB Server

This small Web application project is a port from an Excell sheet. 
At first it was only to keep up with WoT (World of Tanks) data, such as Moes (Mark of Excellences) and their date of obtention and with recent updates Battle Passes as well. 
But it ended up being this WEB application, it's easier to use and I can load it up anywhere on my local network (or extended LAN if using VPN like tailscale), I don't need to have it on my computer at any time.

I started with Flask to host the templates since I already used it for a school project, and I didn't knew how to do backend with any other solutions and for the scale of the project it's totally fine, since I'm the only one user at this point. 
(Maybe I could make a multi-user version with not only my data but other people too, we never know)

And later I added TLS encryption using an NGinx server and using Unicorn in between it and the Flask application. 

It's not the best, but it works totally fine for the small use I have with it.