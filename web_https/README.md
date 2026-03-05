### WEB Server

This small Web Server project is a port from an Excell sheet. 
At first it was only to keep up with WoT (World of Tanks) data, such as Moes (Mark of Excellences) and their date of obtention. 
But it ended up being this WEB application, it's easier to use and I can load it up anywhere on my local network (or extended LAN if using VPN like tailscale), I don't need to have it on my computer at any time.

I started with Flask to host the templates since I already used it for a school project, and I didn't knew how to do backend with any other solutions.
I added TLS encryption using an NGinx server and connecting it to the Flask application using Unicorn. 

It's not the best, but it works totally fine for the small use I have with it. 

Edit 5/03/2026 :
Due to Wargaming's recent actions (concerning increasingly aggressive monetization, unbalanced new branches, a broken matchmaker, no return of promised events, etc.), I have decided to stop my project, simply because without WoT, the project is pointless. That's the problem with having a project based entirely on someone else's idea that develops without your input. At any moment, you can lose everything. That's not the case here, because I still have everything, but my desire to continue developing this tool has died because I've stopped playing, and without that, there's no new data to add, and just adding new tanks and battle passes is pointless and boring as hell. It's a shame because the list of bugs and features to add is as long as my arm, and I would have had work for at least another two years. But I prefer to stop everything, thinking that it was quite an incredible adventure, telling myself that it all started with a damn Excel spreadsheet that was improved into a database and a messed-up project with Flask to display this data, ultimately with the same database but with dynamic images, new data, etc., etc. In over three years, I didn't expect this, but that's how it turned out. 
