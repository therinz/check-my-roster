# check-my-roster

Check-my-roster is a web app that can be used by pilots and cabin crew in a big 
orange European airline. It takes a html-encoded roster file and presents a list 
of all the items with their respective count. This makes it a lot easier to check 
if the variable pay element is correct for that month. 

The app is written in Python and the interaction through the web browser is run 
by Flask. Via a form a html-file can be uploaded which is then parsed using 
BeautifulSoup. A normal roster consists of a table with columns for days and rows 
for roster duties and their characteristics. Via complex switching these items 
are read, saved and counted. The result is then presented back to the user via 
the browser. 

Known bugs:
- Nightstops not included
- Although the count is correct, the UI will indicate more than one ground duty is paid
- New simulator codes LGW and MXP do not work well with checking positioning duties

Room for improvement:
- User interface 

Ideas to implement:
- Import more rosters at a time;
- Select roster files on server, iso uploading
- Incorporate various contractual differences