# 1 Running crawler
An example of how to run the crawler
```bash
pip3 install -r requirements.txt
python3 ycrawler.py -l "./ycrawler.log" -v -r "./data/"
```
It's also possible to use `poetry install`

Other supported command line options are described below
```
-l, --log - log file location, default None
-w, --workers - number of concurrent requests, default is 4
-v, --verbose - turns on DEBUG logging, default is False which is INFO level
-r, --root - root folder for downloaded files storage
-p, --period - period of crawling
```
# 2 FAQ
* News are stored under folders named after their news id
* Sometimes news points to its comment page in that case an InvalidURL error is logged
* When news is downloaded the crawler will not rescan its comments for new links
* You can increase workers number, but be careful as it may influence the number of concurrent open connections to one site
* File names are formed as either a page title or a linked file name limited to 128 symbols
