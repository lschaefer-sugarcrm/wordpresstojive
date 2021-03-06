# Copyright 2017 SugarCRM Inc.  Licensed by SugarCRM under the Apache 2.0 license.

import xml.etree.ElementTree
import requests
from requests.auth import HTTPBasicAuth
import json
import config
from datetime import datetime
import re
import os
import urllib
import urllib2
from bs4 import BeautifulSoup
from operator import itemgetter
from config import jiveUrl, jivePlaceUrlPath

# Add your namespaces here. For example, 'wp': 'http://wordpress.org/export/1.2/'
namespaces = {
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
        
        nameString = ""
        if firstName is not None:
            nameString = firstName
        if lastName is not None:
            if nameString == "":
                nameString = lastName
            else:
                nameString = nameString + " " + lastName
        if nameString == "" and authorNames.get('authorId') is not None:
            nameString = authorNames.get('authorId')
        if nameString != "" and nameString != config.username: 
            content = "<p><i>Post originally written by " + nameString + ".</i></p><p></p>" + content
    
    #Create new paragraphs 
    content = formatParagraphs(content)
    
    #Convert links to posts in the original Wordpress blog to links to new Jive posts
    
    linksRegEx = r'(<a [^>]*?href="https?://' + config.wordpressBlogUrl + '(?:.+?)"(?:.*?)>(?:.*?)</a>)'
    tokens = re.split(linksRegEx, content)
    #Iterate over the WordPress links so we can convert them to Jive links
    for i, token in enumerate(tokens):  
        if re.compile(linksRegEx).match(token):
            
            groups = re.search(r'<a [^>]*?href="https?://' + config.wordpressBlogUrl + '(.+?)"(?:.*?)>(.*?)</a>', token)
            originalUrl = groups.group(1)
            originalLinkText = groups.group(2)
            
            page = urllib2.urlopen("http://" + config.wordpressBlogUrl + originalUrl)
            soup = BeautifulSoup(page, 'html.parser')
            try:
                title = soup.find('h1', attrs={'class', 'post-title'}).text.lower()
            except Exception as e:
                title = soup.find('h2', attrs={'class', 'post-title'}).text.lower()
            title = title.replace(" ", "-")
            title = title.replace(u'\xa0', "-")
            title = re.sub(r'[^-0-9a-zA-Z]+', '', title)
            title = re.sub(r'-+', '-', title)
            
            tokens[i] = '<a href="' + jiveUrl + jivePlaceUrlPath + 'blog/' + originalUrl[0:11] + title + '">' + originalLinkText + '</a>'
             
    #join the tokens back together after updating links
    content = ''.join(tokens)    
    
    #Convert code blocks to pre blocks
    content = content.replace('[code]', '<pre>')
    content = content.replace('[code language="php"]', '<pre>')
    content = content.replace('[code lang="php"]', '<pre>')
    content = content.replace('[/code]', '</pre>')
    
    #Hande Gist code snippets
    gistRegEx = r'((?:http|https)://gist.github.com/[a-zA-Z\d_-]+/[a-zA-Z\d_-]+)'
    tokens = re.split(gistRegEx, content)
    #Iterate over gist links so we can convert them to code embedded on the page
    for i, token in enumerate(tokens):
        #if the gist url is the text for a link, do nothing
        try:
            if tokens[i+1].split('</')[1][:2] == 'a>':
                continue
        except Exception as e:
            pass
        
        #if the gist url is the src for a link, do nothing
        try:
            if tokens[i-1].endswith('href="'):
                continue
        except Exception as e:
            pass
        
        #convert the gist url to a code block
        if re.compile(gistRegEx).match(token):
            tokens[i] = getCodeFromGist(token)
             
    #join the tokens back together after updating gist code snippets
    content = ''.join(tokens)    
    
    
    #Hande Gist tags
    gistRegEx = r'(\[gist\].*?\[/gist\])'
    tokens = re.split(gistRegEx, content)
    #Iterate over gist tags so we can convert them to code embedded on the page
    for i, token in enumerate(tokens):  
        if re.compile(gistRegEx).match(token):
            
            groups = re.search(r'\[gist\](.*?)\[/gist\]', token)
            gistlUrl = groups.group(1)
            
            tokens[i] = getCodeFromGist("http://gist.github.com/" + gistlUrl)
             
    #join the tokens back together after updating gist tags
    content = ''.join(tokens)
    
    
    #Handle images
    
    #Remove image captions
    content = re.sub(r'\[caption.*?\].*?(<img.*?/>).*?\[/caption\]', r'\1', content)
    
    #Split the content on the image tags
    imgTagRegEx = r'(<img.*?src=\".*?\".*?/>)'
    tokens = re.split(imgTagRegEx, content)

    #Iterate over image tags so we can upload them to Jive
    for i, token in enumerate(tokens):
        if re.compile(imgTagRegEx).match(token):
            #Get the original image url
            imageUrl = re.search(r'<img.*?src=\"(.*?)\".*?/>', token).group(1)
            
            #Get the original image's width
            widthSearchResults = re.search(r'width=\"(.*?)\"', token)
            imageWidth = -1
            if widthSearchResults and widthSearchResults.group(1):
                imageWidth = widthSearchResults.group(1)
                try:
                    if int(imageWidth) > 800:
                        imageWidth = "800"
                except Exception as e:
                    print 'Warning! Unable to check image width'
                
            #Download the image
            imageName = imageUrl.split('/')[-1]
            try:
                print urllib.urlretrieve(imageUrl, imageName)
            except Exception as e:
                print e
                tokens[i] = ""
                continue
            
            #Upload the image to Jive and get the new url
            try:
                newImageUrl = uploadImage(imageName, authorNames.get('jiveUsername'))
                os.remove(imageName)
            except RuntimeWarning as e:
                print e
                os.remove(imageName)
                tokens[i] = ""
                continue
            
            #Replace the original token with html for the new image
            if imageWidth != -1:
                tokens[i] = "<br><img src='" + newImageUrl + "' width='" + imageWidth + "'/><br>"
            else:
                tokens[i] = "<br><img src='" + newImageUrl + "'/><br>"
    
    #join the tokens back together after updating images
    content = ''.join(tokens)    
    
    
    
    return content 

def formatParagraphs(textToFormat):
    #Remove tabs
    textToFormat = re.sub(r'(\t)+', '', textToFormat)
    #Remove new lines that come before tags
    textToFormat = re.sub(r'(\n)+<', '<', textToFormat)
    #Replace new lines with closing and opening paragraph tags.
    textToFormat = re.sub(r'(\n)+', '</p><p></p><p>', textToFormat)
    #Add empty space before headings
    textToFormat = re.sub(r'(<h1)+', '<p></p><h1', textToFormat)
    textToFormat = re.sub(r'(<h2)+', '<p></p><h2', textToFormat)
    textToFormat = re.sub(r'(<h3)+', '<p></p><h3', textToFormat)
    textToFormat = re.sub(r'(<h4)+', '<p></p><h4', textToFormat)
    
    return textToFormat

def uploadImage(imageName, jiveUsername):
    print 'Uploading image'
    headers = {
        'Content-Type': 'multipart/form-data',
        'Authorization': 'Bearer ' + access_token,
        'X-Jive-Run-As': 'username ' + jiveUsername,
        'X-JCAPI-Token': config.X_JCAPI_Token
        }
    
    files = {
        'file': (imageName,  
                 open(imageName, 'rb'), 
                 'image/jpg')
        }
    
    r = requests.post(config.jiveUrl + 'api/core/v3/images', headers=headers, files=files)
    if r.status_code == 201:
        newImageUrl = json.loads(r.content).get('ref')
        print 'Successfully uploaded image:' + imageName + '. New url: ' + newImageUrl
        return newImageUrl
    else:
        raise RuntimeWarning('An error occurred while uploading image: ' + imageName + '. ' + str(r.status_code) + ' ' + r.content)  

def getCodeFromGist(gistUrl):
    codeToReturn = ''
    page = urllib2.urlopen(gistUrl)
    soup = BeautifulSoup(page, 'html.parser')
    codeSnippets = soup.find_all('div', attrs={'class', 'js-gist-file-update-container'})
    for snippet in codeSnippets:
        #find the header text
        codeToReturn += '<span style="font-size: 18px;"><strong>'
        codeToReturn += snippet.find('div', attrs={'class', 'file-header'}).find('strong').text.strip()
        codeToReturn += '</strong></span>'
        codeToReturn += '<br>'
         
        #find the code
        codeToReturn += '<pre>'
        codeTableRows = snippet.find('div', attrs={'class', 'blob-wrapper'}).find_all('tr')
        for row in codeTableRows:
            codeToReturn += row.find('td', attrs={'class', 'blob-code'}).renderContents()
            codeToReturn += '<br>'
         
        codeToReturn += '</pre>'
        codeToReturn += '<br>'
    
    return codeToReturn
    
def createBlogPost(title, author, pubDate, content, tags):
    print 'Creating blog post: ' + title
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
        "parent": config.jiveUrl + "api/core/v3/places/" + config.jivePlaceId,
        "tags": tags
        
        }
    r = requests.post(config.jiveUrl + 'api/core/v3/contents', headers=headers, params=params, json=requestBody)
    if r.status_code == 201:
        print 'Successfully created blog post: ' + title
        return r.content
        
    else:
        raise RuntimeError('An error occurred while creating blog post: ' + title + '. ' + str(r.status_code) + ' ' + r.content)
 
def createComment(commentParentUrl, author, date, text):
    print 'Adding comment to: ' + commentParentUrl
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + access_token,
        'X-Jive-Run-As': 'username ' + config.username
        }
    params = {
        "published": date.strftime('%Y-%m-%dT%H:%M:%S +%f'),
        "updated": date.strftime('%Y-%m-%dT%H:%M:%S +%f') #Setting the updated date to be the same as the published date since we don't get an updated date from Wordpress
        }
    requestBody = {
        "content": {
            "type": "text/html",
            "text": "<p><i>Comment originally made by " + author + ".</i></p><p></p>" + text
        },
        "type": "comment",
        }
    r = requests.post(commentParentUrl, headers=headers, params=params, json=requestBody)
    if r.status_code == 201:
        print 'Successfully created comment: ' + json.loads(r.content).get('resources').get('self').get('ref')
        return json.loads(r.content).get('resources').get('comments').get('ref')
        
    else:
        raise RuntimeError('An error occurred while creating comment on: ' + commentParentUrl + '. ' + str(r.status_code) + ' ' + r.content)

def getCommentUrl(responseContent):
    return json.loads(responseContent).get('resources').get('comments').get('ref')

# Get all of the categories associated with a wordpress item
def getTags(item):
    tags = []
    categories = item.findall('category')
    for category in categories:
        tag = category.text
        if tag is not None:
            tag = tag.replace('/', ' & ')
        tags.append(tag)
    return tags

def createComments(blogPostCommentUrl, wordPressItem):
    wordPressComments = wordPressItem.findall('wp:comment', namespaces)
    wordPressCommentsList = []
    for comment in wordPressComments:
        if comment.find('wp:comment_type', namespaces).text == "pingback":
            continue
        
        newComment = {}
        newComment["author"] = comment.find('wp:comment_author', namespaces).text
        newComment["date"] = datetime.strptime(comment.find('wp:comment_date_gmt', namespaces).text + ' GMT', '%Y-%m-%d %H:%M:%S %Z')
        newComment["text"] = formatParagraphs(comment.find('wp:comment_content', namespaces).text)
        newComment["id"] = int(comment.find('wp:comment_id', namespaces).text)
        newComment["parent"] = int(comment.find('wp:comment_parent', namespaces).text)
        wordPressCommentsList.append(newComment)
    wordPressCommentsList = sorted(wordPressCommentsList, key=itemgetter('id'))
    for i, comment in enumerate(wordPressCommentsList):
        commentParentUrl = ""
        if comment["parent"] == 0:
            commentParentUrl = blogPostCommentUrl
        else:
            for com in wordPressCommentsList:
                if(com["id"] == comment["parent"]):
                    commentParentUrl = com["commentUrl"]
                    break
        wordPressCommentsList[i]["commentUrl"] = createComment(commentParentUrl, comment["author"], comment["date"], comment["text"])
    
        
def processWordpressFile():
    authenticateToJive()
    
    root = xml.etree.ElementTree.parse(config.wordpressFileToParse).getroot()
    channel = root.find('channel')
    
    for item in channel.findall('item'):   
        try:
            
            if (item.find('wp:post_type', namespaces).text != 'post'):
                fileName = item.find('wp:attachment_url', namespaces).text.lower()
                if fileName.endswith("png") or fileName.endswith("jpg") or fileName.endswith("jpeg") or fileName.endswith("gif"):
                    continue
                else:
                    print 'Warning! The following item is not being converted: ' + item.find('title').text + '. (' + fileName + ')'
                    continue
            
            title = item.find('title').text
            print 'Found new blog post with title: ' + title
            
            authorNames = getAuthor(item.find('dc:creator', namespaces).text)
            
            content = processBlogContent(item.find('content:encoded', namespaces).text, authorNames)
            
            pubDate = datetime.strptime(item.find('pubDate').text, '%a, %d %b %Y %H:%M:%S +%f')
            
            tags = getTags(item)
            
            responseContent = createBlogPost(title, authorNames.get('jiveUsername'), pubDate, content, tags) 
            
            createComments(getCommentUrl(responseContent), item)

        except Exception as e:
            print
            print ('Error!  A blog post was not successfully created.')
            print e
    
    print 'Blog migration complete.  Woo hoo!'       

processWordpressFile()

