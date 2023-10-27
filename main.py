'''
This module is used for downloading the latest NPR podcasts into a designated media folder.

Eventually I'd like to make it more modular to allow for other podcast websites to be included

Written by Kit Rairigh - https://github.com/krair
'''

import time
import random
import json
import os
import feedparser
import re
import eyed3
import eyed3.id3
from urllib.request import urlretrieve
from dateutil import parser
import podcastparser
import yaml

##### TODO ########
"""
- Move print statements to proper logging
- Add better error detection especially during the download of episodes
    - if file exists, or if the download process cuts and we have an incomplete file
    - If X number of errors with the given podcast, move to the next
    - move the db write operation out to the end of a podcast's run to reduce disk writes
- Notifications of new episodes (or not because already in DB)
- Download podcast images
- For TED RADIO HOUR: "new" podcasts can contain "Listen Again:" which are repeats of older episodes. I should use regex to capture the actual podcast name.
-                    - Can also just contain a year "(2020)" for original broadcast year
-                    - Use the "Original broadcast date:" in the summary? - I should store this as a variable alongside release date
- Also capture the URL to the podcast episode (if exists)
- Sort into correct folders; create new if podcast doesn't exist in database
- Switch to aiohttp and async
- Check how many episodes we should keep, and how many are currently on the system
- Download and put into the db the most recent one, and purge the oldest (after) if we have more than podcast.keep specifies
- Backfill: if 10 most recent are downloaded and in db, and we want the 10 prior? Or if we change 'keep' or get interupted...
    - Episode (track_num) numbering might get messed up in this scenario

- Create a easy way to "save" episodes from being deleted if "keep" exists - can we read "favorited" from jellyfin api?
    - Remove "listened to" but not favorited?

- check for episode number, or use arbitrary counter from the db

- Move to SQLite to avoid a crazy massive json file -- easier to manage I think as well

"""

# To prevent issues with the eyed3 tagger - a lower log level would cause a Traceback
eyed3.log.setLevel("ERROR")


class Podcast:
    """
    A Class to hold the information for the given podcast. Pulls in info from the config file, 
    otherwise uses info given from the podcast when the RSS feed is pulled.
    """
    def __init__(self, settings):
        # The number of episodes we want to keep - for example news older than a week may not interest us
        self.keep = 0
        # Pull any settings from the config file for organization and tagging
        for k,v in settings.items():
          setattr(self, k, v)
        self.feed_url = self.feed
        self.feed = feedparser.parse(self.feed_url)
        self.name = self.feed.feed.title
        try:
          self.author = self.author
        except:
          self.author = self.feed.feed.author_detail.name
        try:
          self.genre = self.genre
        except:
          self.genre = [i.term for i in self.feed.feed.tags]

class Episode:
    """
    A Class to hold the details for a given episode. Used for tagging as well.
    """
    def __init__(self, attributes):
        self.title = attributes.title
        self.artist = podcast.author
        self.album = podcast.name
        self.summary = attributes.summary
        self.release_date = (attributes.published, attributes.summary)
        self.genre = podcast.genre
        self.dl_url = attributes.links[1].href
        self.image_url = attributes.image.href

        # If the podcast has episode numbers built-in, set them here
        #self.track_num = 
    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value):
        # search for "Listen Again:" which is likely a repeated episode.
        regex = re.search('Listen Again: (.*)', value)
        # If found, rename episode to the base name
        if regex:
            self._title = regex.group(1)
        # Otherwise, keep name as is
        else:
            self._title = value
    
    @property
    def release_date(self):
        return self._release_date

    @release_date.setter
    def release_date(self, value):
        self._release_date = str(parser.parse(value[0]).date())

    @property
    def dl_url(self):
        return self._dl_url

    @dl_url.setter
    def dl_url(self, raw_link):
        self._dl_url = raw_link.split('?')[0]

    @property
    def genre(self):
        return self._genre

    @genre.setter
    def genre(self, list):
        self._genre = ', '.join(list)

def load_config():
    # Read and open config.yaml file stored in the same directory as this file
    with open(f'./config.yaml', 'r') as f:
        return yaml.safe_load(f)

def read_db():
    # Read and open the JSON "database" file stored within this directory
    if os.path.isfile('./downloaded_episodes.json'):
        with open('./downloaded_episodes.json', 'r') as f:
            return json.load(f)
    # If the file does not exist, start with an empty file
    else:
        return {'podcasts':[]}

def write_db(data):
    # Write updated information to the db file
    print('Writing to db file')
    with open('./downloaded_episodes.json', 'w') as f:
        json.dump(data, f)

def write_tags(episode):
    #FRONT_COVER = eyed3.id3.frames.ImageFrame.FRONT_COVER
    audiofile = eyed3.load(f"{podpath}/{episode.filename}")
    audiofile.tag.title = episode.title
    audiofile.tag.artist = episode.artist
    audiofile.tag.album = episode.album
    audiofile.tag.release_date = episode.release_date
    audiofile.tag.genre = episode.genre
    # Remove old comment tag as it won't overwrite properly - https://github.com/nicfit/eyeD3/issues/111
    try:
        audiofile.tag.comments.remove(audiofile.tag.comments[0].description, audiofile.tag.comments[0].lang)
    except:
        pass
    audiofile.tag.comments.set(episode.summary, description="")
    audiofile.tag.track_num = episode.track_num
    with open(f"{podpath}/{episode.imagename}", "rb") as cover:
        #audiofile.tag.images.set(FRONT_COVER, cover.read(), "image/jpeg", u"cover")
        audiofile.tag.images.set(3, cover.read(), "image/jpeg", u"cover")

    audiofile.tag.save(version=eyed3.id3.ID3_V2_3)
    print(f"ID3 tags written to {episode.filename}")

# Load config
config = load_config()
# Load config path
path = config['path']
# Try to create path from config file, pass if exists
try:
    os.makedirs(path)
except:
    pass
# Load db
db = read_db()

# Start by selecting each podcast
for _,settings in config['podcasts'].items():
    # Instantiate single podcast from list
    podcast = Podcast(settings)
    print(f"=========Starting {podcast.name}=============")
    # Set path for specific Podcast DL's in our path directory
    podpath = f"{path}/{podcast.author} - {podcast.name}"
    
    # Select Podcast if it exists in the db, otherwise create a new entry
    db_podcast = next(filter(lambda x: x['name'] == podcast.name, db['podcasts']), None)
    new_podcast = False
    if not db_podcast:
        db_podcast = {'name': podcast.name, 
                    'author': podcast.author, 
                    'description': podcast.feed.feed.subtitle,
                    'tags': podcast.genre,
                    'website_url': podcast.feed.feed.links[0].href,
                    'feed_url': podcast.feed_url,
                    'image_url': podcast.feed.feed.image.href,
                    'episodes': []
                   }
        try:
            os.makedirs(podpath)
        except:
            pass
        new_podcast = True

    # Download only the latest # of episodes defined by the 'keep' attribute
    if new_podcast == True:
        # If new, the list is reversed to allow correct episode numbering 
        feed_list = reversed(podcast.feed.entries[0:podcast.keep])
        # Append the new podcast to the database
        db['podcasts'].append(db_podcast)
    else: 
        feed_list = podcast.feed.entries[0:podcast.keep]
        #This section doesn't necessarily work correctly. Especially if a track is missing in the middle
        previous_episode_num = db_podcast['episodes'][0]['track_num']
        previous_episode_index = next(filter(lambda x: x[1]['title'] == db_podcast['episodes'][0]['title'], enumerate(podcast.feed.entries)), None)[0]
    
    # Look for repeated episodes (already downloaded) 
    repeats = 0
    # To help with episode numbering
    new_episode_counter = 0
    # Go through each episode in our list
    for i in feed_list:
        # Perhaps make this configurable
        if repeats < 3:
            episode = Episode(i)
            # Check if episode exists in db, if not, continue to download
            if next(filter(lambda x: x['title'] == episode.title, db_podcast['episodes']), None):
                print(f'Episode: "{episode.title}" already downloaded')
                repeats += 1
            else:
                repeats = 0
                new_episode_counter += 1
                # set episode number (this section also needs review)
                try:
                    print(f"Downloading {episode.track_num}: {episode.title}")
                except:
                    if new_podcast == True: 
                        episode.track_num = new_episode_counter
                    else: episode.track_num = previous_episode_num + previous_episode_index - new_episode_counter
                    print(f"Downloading {episode.track_num}: {episode.title}")
                # Download  episode audio file
                episode.filename = episode.title.replace(' ', '_') + '.mp3'
                # Configurable?
                remaining_download_tries = 5
                while remaining_download_tries > 0 :
                    try:
                        urlretrieve(episode.dl_url, f"{podpath}/{episode.filename}")
                        print("successfully downloaded: " + episode.filename)
                    except:
                        print("error downloading " + episode.filename +" on try no " + str(6 - remaining_download_tries))
                        remaining_download_tries -= 1
                        continue
                    else:
                        break
                # Download episode artwork/image
                episode.imagename = episode.title.replace(' ','_') + '.jpg'
                remaining_download_tries = 5
                while remaining_download_tries > 0 :
                    try:
                        urlretrieve(episode.image_url, f"{podpath}/{episode.imagename}")
                        print("successfully downloaded image: " + episode.imagename)
                    except:
                        print("error downloading image " + episode.imagename +" on try no " + str(6 - remaining_download_tries))
                        remaining_download_tries -= 1
                        continue
                    else:
                        break
                
                # Write ID3 tags to file
                write_tags(episode)
            
                # Insert episode data into db episode list
                # Use regex to remove underscores from non-public attributes as dictionary keys (like '_title')
                regtest = '^_?(.*)'
                episode_data = {re.search(regtest,k).group(1):v for (k,v) in episode.__dict__.items()}
                db_podcast['episodes'].insert(new_episode_counter - 1,episode_data)
                # Write progress thus far to the db file
                write_db(db)
                # Sleep to prevent hitting request rate-limits
                time.sleep(100)
        else:
            print("Reached 3 repeated episodes, breaking loop")
            break