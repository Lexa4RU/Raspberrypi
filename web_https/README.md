### WEB Server

This small Web Server project is a port from an Excell sheet. 
At first it was only to keep up with WoT (World of Tanks) data, such as Moes (Mark of Excellences) and their date of obtention. 
But it ended up being this WEB Server, it's easier to use and I can load it up anywhere on my local network, I don't need to have it on my computer.

I started with Flask to host the templates since I already used it for a school project, and I didn't knew how to do backend with any other solutions.
I added TLS encryption using an NGinx server and connecting it to the Flask application using Unicorn. 

It's not the best, but it works totally fine for the small use I have with it. 
