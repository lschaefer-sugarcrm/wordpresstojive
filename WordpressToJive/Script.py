import xml.etree.ElementTree
import requests
from requests.auth import HTTPBasicAuth
import json
import config
from datetime import datetime
import re

namespaces = {
    'content': 'http://purl.org/rss/1.0/modules/content/',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'wp': 'http://wordpress.org/export/1.2/'
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
    
def getJiveUsername(firstName, lastName):
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + access_token
        }
    r = requests.get(config.jiveUrl + 'api/core/v3/search/people?filter=search(' + firstName + ',' + lastName + ')', headers=headers)
    if r.status_code == 200:       
        return json.loads(r.content).get('list')[0].get('jive').get('username')
    else:
        raise RuntimeError('An error occurred while getting the the username for ' + firstName + ' ' + lastName + '. ' + str(r.status_code) + ' ' + r.content)

#use the authorId from the <dc:creator> tag to get the creator's first and last names from the Wordpress file     
def getAuthorNames(authorId):
    authorNames = {
        "authorId": authorId
    }
    
    authors = xml.etree.ElementTree.parse(config.wordpressFileToParse).getroot().find('channel').findall('wp:author', namespaces)
    for author in authors:
        if author.find('wp:author_login', namespaces).text == authorId:
            authorNames["firstName"] = author.find('wp:author_first_name', namespaces).text
            authorNames["lastName"] = author.find('wp:author_last_name', namespaces).text
            return authorNames
    return authorNames

# Check to see if we can find an author id in Jive for the Wordpress author.
# If not, we'll set the author to the currently logged in user    
def getAuthor(authorId):
    authorNames = getAuthorNames(authorId);
    try:
        if authorNames.get('firstName') is not None and authorNames.get('lastName') is not None:
            authorNames['jiveUsername'] = getJiveUsername(authorNames.get('firstName'), authorNames.get('lastName'))
            return authorNames
    except Exception as e:
        print ('An error occurred while trying to get the Jive username associated with ' + authorId + '. The authorId will be set to ' + config.username)
        print e
    authorNames['jiveUsername'] = config.username
    return authorNames   

def processBlogContent(content, authorNames):
    if content is None:
        return content
    
    #If we weren't able to set the blog author, we'll add a sentence to the top of the post saying
    # who originally wrote the post.
    if authorNames.get('jiveUsername') is config.username:
        firstName = authorNames.get('firstName')
        lastName = authorNames.get('lastName')
        
        nameString = None
        if firstName is not None:
            nameString = firstName
        if lastName is not None:
            nameString = nameString + " " + lastName
        if nameString is None and authorNames.get('authorId') is not None:
            nameString = authorNames.get('authorId')
        if nameString is not None:
            content = "<p><i>Post originally written by " + nameString + ".</i></p><p></p>" + content
    
    #Create new paragraphs 
    #Remove tabs
    content = re.sub(r'(\t)+', '', content)
    #Remove new lines that come before tags
    content = re.sub(r'(\n)+<', '<', content)
    #Replace new lines with closing and opening paragraph tags.
    content = re.sub(r'(\n)+', '</p><p></p><p>', content)
    #Add empty space before headings
    content = re.sub(r'(<h1)+', '<p></p><h1', content)
    content = re.sub(r'(<h2)+', '<p></p><h2', content)
    content = re.sub(r'(<h3)+', '<p></p><h3', content)
    content = re.sub(r'(<h4)+', '<p></p><h4', content)
    
    return content 
    
def createBlogPost(title, author, pubDate, content):
    print 'Creating blog post'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + access_token,
        'X-Jive-Run-As': 'username ' + author
        }
    params = {
        "published": pubDate.strftime('%Y-%m-%dT%H:%M:%S +%f'),
        "updated": pubDate.strftime('%Y-%m-%dT%H:%M:%S +%f') #Setting the updated date to be the same as the published date since we don't get an updated date from Wordpress
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
    r = requests.post(config.jiveUrl + 'api/core/v3/contents', headers=headers, params=params, json=requestBody)
    if r.status_code == 201:
        print 'Successfully created blog post: ' + title
    else:
        raise RuntimeError('An error occurred while creating blog post: ' + title + '. ' + str(r.status_code) + ' ' + r.content)
    
def processWordpressFile():
    authenticateToJive()
    
    root = xml.etree.ElementTree.parse(config.wordpressFileToParse).getroot()
    channel = root.find('channel')
    
    for item in channel.findall('item'):   
        try:
            title = item.find('title').text
            
            authorNames = getAuthor(item.find('dc:creator', namespaces).text)
            
            content = processBlogContent(item.find('content:encoded', namespaces).text, authorNames)
            
            pubDate = datetime.strptime(item.find('pubDate').text, '%a, %d %b %Y %H:%M:%S +%f')
            createBlogPost(title, authorNames.get('jiveUsername'), pubDate, content) 
        except Exception as e:
            print
            print ('Warning!  A blog post was not successfully created.')
            print e
           


processWordpressFile()

