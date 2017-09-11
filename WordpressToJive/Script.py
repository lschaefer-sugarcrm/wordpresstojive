import xml.etree.ElementTree
import requests
from requests.auth import HTTPBasicAuth
import json
import config

namespaces = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/'
    }

access_token = ""

# Authenticate to Jive and get the access token the other requests will use   
def authenticateToJive():
    print 'Authenticating to Jive'
    payload = (
        ('grant_type', 'password'),
        ('username', config.username),
        ('password', config.password)
        )
    r = requests.post(config.jiveUrl + 'oauth2/token', auth=HTTPBasicAuth(config.client_id, config.client_secret), data=payload)
    if r.status_code != 200:
        raise RuntimeError('Unable to authenticate to Jive. ' + str(r.status_code) + ' ' + r.content)
    global access_token;
    access_token = json.loads(r.content).get('access_token')
    if not access_token:
        raise ValueError('Unable to get access token from response. ' + str(r.status_code) + ' ' + r.content)
    print 'Successfully authenticated and parsed access token.'
    
def createBlogPost(title, author, content):
    print 'Creating blog post'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + access_token,
        }
    requestBody = {
        "content": {
            "type": "text/html",
            "text": content
        },
        "subject": title,
        "type": "post",
        "parent": config.jiveUrl + "api/core/v3/places/" + config.jivePlaceId
        
        }
    r = requests.post(config.jiveUrl + 'api/core/v3/contents', headers=headers, json=requestBody)
    if r.status_code == 201:
        print 'Successfully created blog post: ' + title
    else:
        raise RuntimeError('An error occurred while creating blog post: ' + title + '. ' + str(r.status_code) + ' ' + r.content)
    
def processWordpressFile():
    root = xml.etree.ElementTree.parse(config.wordpressFileToParse).getroot()
    channel = root.find('channel')
    for item in channel.findall('item'):
        title = item.find('title').text
        author = item.find('dc:creator', namespaces).text
        content = item.find('content:encoded', namespaces).text
        createBlogPost(title, author, content)    

authenticateToJive()
processWordpressFile()

