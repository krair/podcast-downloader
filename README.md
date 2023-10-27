# podcast-downloader
Download and tag podcasts for offline listening. Currently only tested on [NPR](https://www.npr.org/podcasts-and-shows/) podcasts and shows. Eventually I'd like to make it more flexible, but this works for now.

Still very much a work in progress. Use the `config.yaml.example` file as a starting point. For now the only required pieces are the podcast name, the feed URL of the RSS feed, and the number of episodes you'd like to keep.

Install the required pip packages in the `requirements.txt` file.

**Currently there is no easy way to delete episodes (through this program) to make room for more episodes once you've reached the keep limit. Deleting the local file will make space on the drive, but the episode will still be in the database. You could delete the episode entry in the database's .json file, but do so at your own risk.** 

The program currently has a hard coded 100 second sleep timer running between episode downloads to reduce the chance of rate-limiting, which you will likely hit anyways if you are downloading 50+ episodes in one go. I don't know when the limit is reset if you hit this limit.