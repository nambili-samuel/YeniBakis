# BlueSky AI Bot

For months, I have been actively getting my hands dirty building social media bots, from WhatsApp and Telegram to X and Bluesky, including website bots. A bot seemed like the best way forward.

I have built bots from scratch before, but this time I created a fully self-running Bluesky bot hosted on GitHub Actions. This free, open-source project takes a much more hands-off approach: complete automation with no human oversight needed once the bot is deployed. It is not as terrifying as it sounds, especially since I intended to keep things straightforward.

The bot's workflow is simple: scrape a landing page, retrieve news and related images from the website, scrape YouTube, summarise each piece of content, and then post it to Bluesky. Easy!

The entire process, from initial scrape to final social media post, takes no more than a few seconds. While there is a large ecosystem of libraries available, like npm for Node.js which offers packages for scraping, APIs, databases, and more, I chose Python, my favourite programming language. This allowed me to leverage existing, well-tested libraries and saved considerable time and effort.

GitHub Actions provides critical infrastructure for the bot in several ways. Automation: We use scheduled workflows to run the bot regularly, automatically scraping for new content and posting to Bluesky. Testing, optional but good practice: GitHub Actions can also run tests automatically whenever code is updated, ensuring everything works correctly. Cost: It is free for public repositories and often sufficient for private projects, offering a generous tier for smaller automation tasks.

You can customise the bot to your liking. Change the scraping targets, refine the LLM prompts, extend posting functionality, or add new features. Drop a pull request if you need help with deployment or running it.

Credit goes to Dr. Nambili Samuel, the AI researcher and developer who built this AI agent for social media automation.



## Features

- Automatic RSS monitoring
- Website and YouTube feed support
- Intelligent thumbnail extraction
- Image optimization and compression
- Duplicate prevention
- Turkish character support
- Error handling and logging

## Installation

### Prerequisites
- Python 3.8+
- BlueSky account 

### Dependencies
```bash
pip install feedparser requests atproto pillow
