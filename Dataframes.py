import pandas as pd

calendar = pd.read_csv("calendar.txt",parse_dates=["start_date", "end_date"],date_format="%Y%m%d")
calendar_dates = pd.read_csv("calendar_dates.txt", parse_dates=["date"],date_format="%Y%m%d")
frequencies = pd.read_csv("frequencies.txt")
levels = pd.read_csv("levels.txt")
pathways = pd.read_csv("pathways.txt")
routes = pd.read_csv("routes.txt")
stops = pd.read_csv("stops.txt")
trips = pd.read_csv("trips.txt")
