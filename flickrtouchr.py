#!/usr/bin/python3

#
# FlickrTouchr - a simple python script to grab all your photos from flickr, 
#                dump into a directory - organised into folders by set - 
#                along with any favourites you have saved.
#
#                You can then sync the photos to an iPod touch.
#
# Version:       1.3
#
# Original Author: colm@allcosts.net - Colm MacCarthaigh - 2008-01-21
#
# Modified by:     Dan Benjamin - http://hivelogic.com
#
# License:         Apache 2.0 - http://www.apache.org/licenses/LICENSE-2.0.html
#
# References:
# http://hivelogic.com/articles/backing-up-flickr/
# https://github.com/aligature/hivelogic-flickrtouchr (this fork)
# https://github.com/dan/hivelogic-flickrtouchr (orig)
# https://github.com/l0b0/hivelogic-flickrtouchr (another fork)

import xml.dom.minidom
import webbrowser
import urllib.parse
import urllib.request, urllib.error, urllib.parse
import unicodedata
import pickle
import hashlib
import sys
import os
import traceback
from optparse import OptionParser

API_KEY       = "e224418b91b4af4e8cdb0564716fa9bd"
SHARED_SECRET = "7cddb9c9716501a0"

#
# Utility functions for dealing with flickr authentication
#
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc

def getString(dom, tag):
    dir = getText(dom.getElementsByTagName(tag)[0].childNodes)
    return dir

def getTitle(dom):
    return getString(dom, "title")

#
# Get the frob based on our API_KEY and shared secret
#
def getfrob():
    # Create our signing string
    string = SHARED_SECRET + "api_key" + API_KEY + "methodflickr.auth.getFrob"
    hash   = hashlib.md5(string.encode("utf8")).hexdigest()

    # Formulate the request
    url    = "https://api.flickr.com/services/rest/?method=flickr.auth.getFrob"
    url   += "&api_key=" + API_KEY + "&api_sig=" + hash

    try:
        # Make the request and extract the frob
        response = urllib.request.urlopen(url)

        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # get the frob
        frob = getText(dom.getElementsByTagName("frob")[0].childNodes)

        # Free the DOM 
        dom.unlink()

        # Return the frob
        return frob
    except Exception:
        print ("Could not retrieve frob")

#
# Login and get a token
#
def froblogin(frob, perms):
    string = SHARED_SECRET + "api_key" + API_KEY + "frob" + frob + "perms" + perms
    hash   = hashlib.md5(string.encode("utf8")).hexdigest()

    # Formulate the request
    url    = "https://api.flickr.com/services/auth/?"
    url   += "api_key=" + API_KEY + "&perms=" + perms
    url   += "&frob=" + frob + "&api_sig=" + hash

    # Tell the user what's happening
    print("In order to allow FlickrTouchr to read your photos and favourites")
    print("you need to allow the application. Please press return when you've")
    print("granted access at the following url (which should have opened")
    print("automatically).")
    print()
    print(url)
    print()
    print("Waiting for you to press return")

    # We now have a login url, open it in a web-browser
    webbrowser.open_new(url)

    # Wait for input
    sys.stdin.readline()

    # Now, try and retrieve a token
    string = SHARED_SECRET + "api_key" + API_KEY + "frob" + frob + "methodflickr.auth.getToken"
    hash   = hashlib.md5(string.encode("utf8")).hexdigest()
    
    # Formulate the request
    url    = "https://api.flickr.com/services/rest/?method=flickr.auth.getToken"
    url   += "&api_key=" + API_KEY + "&frob=" + frob
    url   += "&api_sig=" + hash

    # See if we get a token
    try:
        # Make the request and extract the frob
        response = urllib.request.urlopen(url)

        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # get the token and user-id
        token = getText(dom.getElementsByTagName("token")[0].childNodes)
        nsid  = dom.getElementsByTagName("user")[0].getAttribute("nsid")

        # Free the DOM
        dom.unlink()

        # Return the token and userid
        return (nsid, token)
    except Exception:
        print("Login failed")

# 
# Sign an arbitrary flickr request with a token
# 
def flickrsign(url, token):
    query  = urllib.parse.urlparse(url).query
    query += "&api_key=" + API_KEY + "&auth_token=" + token
    params = query.split('&') 

    # Create the string to hash
    string = SHARED_SECRET
    
    # Sort the arguments alphabettically
    params.sort()
    for param in params:
        string += param.replace('=', '')
    hash   = hashlib.md5(string.encode("utf8")).hexdigest()

    # Now, append the api_key, and the api_sig args
    url += "&api_key=" + API_KEY + "&auth_token=" + token + "&api_sig=" + hash
    
    # Return the signed url
    return url

#
# Grab the photo from the server
#
def getphoto(id, token, filename):
    try:
        # Contruct a request to find the sizes
        url  = "https://api.flickr.com/services/rest/?method=flickr.photos.getSizes"
        url += "&photo_id=" + id

        # Sign the request
        url = flickrsign(url, token)

        # Make the request
        response = urllib.request.urlopen(url)

        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # Get the list of sizes
        sizes =  dom.getElementsByTagName("size")

        # Grab the original if it exists
        allowedTags = ("Original", "Video Original", "Large", "Large 2048")
        largestLabel = sizes[-1].getAttribute("label")
        #print "%s" % [i.getAttribute("label") for i in sizes]
        if (largestLabel in allowedTags):
          imgurl = sizes[-1].getAttribute("source")
        else:
          print("Failed to get %s for photo id %s" % (largestLabel, id))

        # Free the DOM memory
        dom.unlink()

        # Grab the image file
        response = urllib.request.urlopen(imgurl)
        data = response.read()

        # Save the file!
        fh = open(filename, "wb")
        fh.write(data)
        fh.close()

        return filename
    except Exception:
        print("Failed to retrieve photo id " + id)

def getUser():
    # First things first, see if we have a cached user and auth-token
    try:
        cache = open("touchr.frob.cache", "rb")
        config = pickle.load(cache)
        cache.close()

    # We don't - get a new one
    except Exception:
        (user, token) = froblogin(getfrob(), "read")
        config = { "version":1 , "user":user, "token":token }  

        # Save it for future use
        cache = open("touchr.frob.cache", "wb")
        pickle.dump(config, cache)
        cache.close()
    return config

def setUrls(setId, urls, config):
    url = "https://api.flickr.com/services/rest/?method=flickr.photosets.getInfo"
    url += "&photoset_id=" + setId
    url = flickrsign(url, config["token"])

    try:
        response = urllib.request.urlopen(url)
    except Exception:
        print("Failed to performrequest [%s]" % url)
        exit(1)
    dom = xml.dom.minidom.parse(response)
    sets =  dom.getElementsByTagName("photoset")

    # For each set - create a url
    for set in sets:
        dir = getTitle(set).replace("\\", "_").replace("/", "_")

        # Make sure set's dir is not empty
        if dir.strip() == "":
            dir = setId

        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.photosets.getPhotos"
        url  += "&extras=original_format,media,last_update"
        url  += "&photoset_id=" + setId

        # Append to our list of urls
        urls.append( (url , dir) )
    
    return urls

def userUrls(userId, tags, urls, config):
    url = "https://api.flickr.com/services/rest/?method=flickr.people.getInfo"
    url += "&user_id=" + userId
    url = flickrsign(url, config["token"])

    response = urllib.request.urlopen(url)
    dom = xml.dom.minidom.parse(response)
    person =  dom.getElementsByTagName("person")[0]
    username = getString(person, "username")

    if not tags:
        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.favorites.getList"
        url  += "&user_id=" + userId
        url  += "&extras=last_update"
    else:
        url   = "https://api.flickr.com/services/rest/?method=flickr.photos.search"
        url  += "&user_id=" + userId
        url  += "&tags=" + tags
        url  += "&extras=last_update"

    # Append to our list of urls
    urls.append( (url , '%s - %s' % (username, tags)) )
    return urls

def allUrls(urls, printSets, config):
    # Now, construct a query for the list of photo sets
    url  = "https://api.flickr.com/services/rest/?method=flickr.photosets.getList"
    url += "&user_id=" + config["user"]
    url  = flickrsign(url, config["token"])

    # get the result
    response = urllib.request.urlopen(url)
    
    # Parse the XML
    dom = xml.dom.minidom.parse(response)

    # Get the list of Sets
    sets =  dom.getElementsByTagName("photoset")

    # For each set - create a url
    for set in sets:
        pid = set.getAttribute("id")
        dir = getTitle(set).replace("\\", "_").replace("/", "_")

        # Make sure set's dir is not empty
        if dir.strip() == "":
            dir = pid

        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.photosets.getPhotos"
        url  += "&extras=original_format,media,last_update"
        url  += "&photoset_id=" + pid

        if printSets:
            print("[" + pid + "] [" + dir + "]")
            print(url)

        # Append to our list of urls
        urls.append( (url , dir) )

    # Free the DOM memory
    dom.unlink()

    urls.reverse()

    # Add the photos which are not in any set
    url   = "https://api.flickr.com/services/rest/?method=flickr.photos.getNotInSet"
    url  += "&extras=original_format,media,last_update"
    urls.append( (url, "No Set") )

    # Add the user's Favourites
    url   = "https://api.flickr.com/services/rest/?method=flickr.favorites.getList"
    url  += "&extras=original_format,media,last_update"
    urls.append( (url, "Favourites") )
    
    return urls

def getNewPhotos(urls, config):
    # Time to get the photos
    inodes = {}
    newFiles = []
    for (url , dir) in urls:
        # Create the directory
        try:
            os.makedirs(dir)
        except Exception:
            if os.path.isdir(dir):
                print("Warning: Directory [%s] already exists" % dir)
                pass
            else:
                print("Error: Couldn't create directory [%s]" % dir)

        # Get 500 results per page
        url += "&per_page=500"
        pages = page = 1

        while page <= pages: 
            request = url + "&page=" + str(page)

            # Sign the url
            request = flickrsign(request, config["token"])

            # Make the request
            response = urllib.request.urlopen(request)

            # Parse the XML
            dom = xml.dom.minidom.parse(response)

            # Get the total
            try:
                pages = int(dom.getElementsByTagName("photo")[0].parentNode.getAttribute("pages"))
            except IndexError:
                pages = 0

            # Grab the photos
            for photo in dom.getElementsByTagName("photo"):
                # Tell the user we're grabbing the file

                # Grab the id, name and last update
                photoid = photo.getAttribute("id")
                photoname = photo.getAttribute("title")
                last_update = int(photo.getAttribute("lastupdate"))

                # Detect media type
                media = photo.getAttribute("media")
                if media == "video":
                    extension = ".mov"
                else:
                    extension = ".jpg"

                # The target
                if photoname.strip() == "":
                    photoname = photoid

                target = '%s/%s%s' % (dir, photoname.replace("\\", "-").replace("/", "-"), extension)

                # Record files that exist
                if os.access(target, os.R_OK):
                    inodes[photoid] = target
                    mtime = os.path.getmtime(target)
                    if last_update > int(mtime):
                        newFiles.append((photo, target))
                        print("Updated photo [%s] in set [%s]" % (photoname, dir))
                    else:
                        print("Not updated  photo [%s] to set [%s]" % (photoname, dir))
                else:
                    newFiles.append((photo, target))
                    print("Adding photo [%s] to set [%s]" % (photoname, dir))

            # Move on the next page
            page = page + 1

    return (newFiles, inodes)

def downloadPhotos(newFiles, inodes, config):
    for (photo, target) in newFiles:
        # Look it up in our dictionary of inodes first
        photoid = photo.getAttribute("id")
        if photoid in inodes and inodes[photoid] and os.access(inodes[photoid], os.R_OK):
            # We have it already
            print('Warning: Photo [%s](%s) already exists as [%s]' % (target, photoid, inodes[photoid]))
            #os.link(inodes[photoid], target)
            getphoto(photo.getAttribute("id"), config["token"], target)
        else:
            print('Downloading photo [%s](%s)' % (target, photoid))
            inodes[photoid] = getphoto(photo.getAttribute("id"), config["token"], target)

######## Main Application ##########
def main():
    # The first, and only argument needs to be a directory

    parser = OptionParser()
    parser.add_option("-s", "--setid", dest="setid",
            help="optional specific set to download")
    parser.add_option("-u", "--userid", dest="userid",
            help="optional specific user's favorites or tags to download")
    parser.add_option("-t", "--tags", dest="tags",
            help="optional specific user's tags to download")
    parser.add_option("-d", "--destination", dest="destination",
            help="directory to save backup")
    parser.add_option("-p", "--print-sets", dest="printSets", action="store_true", default=False,
            help="only print set info")
    (options, args) = parser.parse_args()

    setId = None
    userId = None
    tags = None
    printSets = options.printSets
    try:
        destination = options.destination
        setId = options.setid
        userId = options.userid
        tags = options.tags
        os.chdir(destination)
    except Exception as e:
        parser.print_help()
        sys.exit(255)

    try:
        config = getUser()

        urls = []

        if setId:
            urls = setUrls(setId, urls, config)

        elif userId:
            urls = userUrls(userId, tags, urls, config)

        else:
            urls = allUrls(urls, printSets, config)

        if printSets:
            exit(1)

        (newFiles, inodes) = getNewPhotos(urls, config)

        downloadPhotos(newFiles, inodes, config)

    except Exception as e:
        print(traceback.format_exc())
        print(type(e).__name__, e)

if __name__ == '__main__':
   try:
      main()
   except urllib.error.URLError:
      pass
