from flask import Flask, render_template, request, session, redirect, url_for, send_file
import os
import uuid
import hashlib
import pymysql.cursors
from functools import wraps
import time

app = Flask(__name__)
app.secret_key = "super secret key"
IMAGES_DIR = os.path.join(os.getcwd(), "images")

connection = pymysql.connect(host="localhost",
                             user="root",
                             password="",
                             db="finstagram",
                             charset="utf8mb4",
                             port=3306,
                             cursorclass=pymysql.cursors.DictCursor,
                             autocommit=True)

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if not "username" in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return dec

# takes in a query ( and optionally a return type
# and parameters ) and executes the query
def runQuery( query, returnType = None, parameters = None ):
    with connection.cursor( ) as cursor:
        cursor.execute( query, parameters )
    if returnType == "one":
        return cursor.fetchone( )
    if returnType == "many":
        return cursor.fetchmany( )
    if returnType == "all":
        return cursor.fetchall( )
    return
    
def grabAllPhotoData( ):
    username = session[ "username" ]
    # set and execute query to get data on all photos
    query = "SELECT * FROM Liked RIGHT OUTER JOIN \
            (photo JOIN person ON( photo.photoOwner = person.username ) )\
            USING( photoID )\
            ORDER BY Photo.timestamp ASC, Liked.timestamp ASC"
    query = "SELECT * FROM Tag RIGHT OUTER JOIN ( Liked RIGHT OUTER JOIN\
            (photo JOIN person ON( photo.photoOwner = person.username ) )\
            USING( photoID ) ) USING( photoID )\
            ORDER BY Photo.timestamp ASC, Liked.timestamp ASC"
    data = runQuery( query, "all" )
    # data to handle each photo:
    # dictionary with the format:
    # { 
    #   photoID: [
    #       filepath, 
    #       photoOwner,
    #       firstName + lastName of photo owner,
    #       timestamp,
    #       [list of users who liked],
    #       True/False if user has liked photo,
    #       caption,
    #       True/False if user is owner (for deletion of photos)
    #  ]
    # }
    photoData = { }
    for item in data:
        filePath = item[ "filePath" ]
        photoID = item[ "photoID" ]
        photoOwner = item[ "photoOwner" ]
        firstName = item[ "fname" ]
        lastName = item[ "lname" ]
        timestamp = item[ "timestamp" ]
        likerUsername = item[ "likerUsername" ]
        caption = item[ "caption" ]
        allFollowers = item[ "allFollowers" ]
        
        # if we are not the photo owner, run through allFollowers
        # tests
        if photoOwner != username:
            # if allFollowers was checked, 
            # run query to grab followers of the photoOwner
            # if photoOwner has no followers OR current user is not 
            # a follower of photoOwner, COTINUE (DO NOT SHOW PHOTO)
            if allFollowers:
                query = "SELECT followerUsername\
                        FROM Follow\
                        WHERE followeeUsername = %s AND acceptedFollow = True" 
                data = runQuery( query, "one", photoOwner )
                if not data or data[ "followerUsername" ] != username:
                    continue
            # else if allFollowers was not checked,
            # check to see if the photoID is in the same group the 
            # current user is in. if not, CONTINUE (DO NOT SHOW PHOTO)
            else:
                query = "SELECT username\
                        FROM Belong NATURAL JOIN Share\
                        WHERE PhotoID = %s AND username = %s" 
                data = runQuery( query, "one", ( photoID, username ) )
                if not data:
                    continue

        # if photoID not in dictionary, add it 
        # and set followers list to empty and set liked status 
        # to False
        # set userIsOwner if user is owner of photo (for deletion
        # of photo purposes)
        if photoID not in photoData:
            photoData[ photoID ] = [ filePath, photoOwner, \
                                    firstName + " " + lastName,\
                                    timestamp, [ ], False, caption, \
                                    True if username == photoOwner else False  ]
        photoData[ photoID ][ 4 ].append( likerUsername )
        
        # if the user liked the photo (if the current user and photoID
        # is in the Liked table), then set its liked status to True
        if likerUsername == session[ "username" ]:
            photoData[ photoID ][ 5 ] = True
    # pass dictionary into images page
    return photoData

# main page
@app.route("/")
def index():
    # if user is logged in, redirect to home page
    # else return welcome page
    if "username" in session:
        return redirect(url_for("home"))
    return render_template("index.html")

# home page
@app.route("/home")
@login_required
def home():
    return render_template("home.html", username=session["username"])

# upload photo page. login required
@app.route("/upload", methods=["GET"])
@login_required
def upload():
    return render_template("upload.html")

# users images page. login required
@app.route("/images", methods=["GET"], defaults = {"error": None } )
@app.route("/images?<error>", methods=["GET"])
@login_required
def images( error ):
    # ============
    # the following is only if the user
    # likes or dislikes a photo

    # grab the photoID and option (like/unlike) from url
    username = session[ "username" ]
    photoID = request.args.get( "photoID" )
    option = request.args.get( "option" )
    # if user clicked unlike, remove from liked table.
    # else, add to liked table
    # if user clicked delete photo, delete the photo (w photoID)
    # from photo, tag, liked, caption table
    try:
        if option == "unlike":
            query = "DELETE FROM Liked WHERE likerUsername = %s AND\
                    photoID = %s"
            runQuery( query, None, ( username, photoID ) )
        elif option == "like":
            query = "INSERT INTO Liked VALUES( %s, %s, %s )"
            runQuery( query, None, ( username, photoID, \
                    time.strftime('%Y-%m-%d %H:%M:%S') ) )
        elif option == "delete":
            query = "DELETE FROM Photo WHERE photoID = %s"
            runQuery( query, None, photoID )
            query = "DELETE FROM Share WHERE photoID = %s"
            runQuery( query, None, photoID )
            query = "DELETE FROM Liked WHERE photoID = %s"
            runQuery( query, None, photoID )
            query = "DELETE FROM Tag WHERE photoID = %s"
            runQuery( query, None, photoID )
            query = "DELETE FROM Comment WHERE photoID = %s"
            runQuery( query, None, photoID )

    except pymysql.err.IntegrityError:
        return redirect( url_for( "images" ) )
    # ============
    # grab all photo data and render template
    photoData = grabAllPhotoData( )
    return render_template("images.html", error = error, images = photoData )

# image page ( url for a single image )
@app.route("/image/<image_name>", methods=["GET"])
def image(image_name):
    image_location = os.path.join(IMAGES_DIR, image_name)
    if os.path.isfile(image_location):
        return send_file(image_location, mimetype="image/jpg")

# login page
@app.route("/login", methods=["GET"])
def login():
    return render_template("login.html")

# new user registration page
@app.route("/register", methods=["GET"])
def register():
    return render_template("register.html")

# authenticating user page ( from login )
@app.route("/loginAuth", methods=["POST"])
def loginAuth():
    if request.form:
        # grab entered username and password 
        username = request.form["username"]
        plaintextPasword = request.form["password"]
        # hash password to compare with hashed stored in database
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()

        # execute query to find corresponding username and password
        query = "SELECT * FROM person WHERE username = %s AND password = %s"
        data = runQuery( query, "one", ( username, hashedPassword ) )
        
        # if entry exists, redirect to homepage with corresponding username
        # else, return user does not exist/incorrect username or password
        if data:
            session["username"] = username
            return redirect(url_for("home"))
        
        error = "Incorrect username or password."
        return render_template("login.html", error=error)

    error = "An unknown error has occurred. Please try again."
    return render_template("login.html", error=error)

# authenticating new user page 
@app.route("/registerAuth", methods=["POST"])
def registerAuth():
    if request.form:
        # grab corresponding username, hashed password, first name, last name
        username = request.form["username"]
        plaintextPasword = request.form["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        firstName = request.form["fname"]
        lastName = request.form["lname"]
        
        # execute query: if username exists, return an error
        # else, add to database and redirect to login 
        try:
            query = "INSERT INTO person (username, password, fname, lname) VALUES (%s, %s, %s, %s)"
            runQuery( query, None, ( username, hashedPassword, firstName, lastName ) )
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % ( username )
            return render_template('register.html', error = error )    

        return redirect(url_for("login"))

    error = "An error has occurred. Please try again."
    return render_template("register.html", error=error)

# logout page
@app.route("/logout", methods=["GET"])
def logout():
    session.pop("username")
    return redirect("/")

# image uploaded page
@app.route("/uploadImage", methods=["POST"])
@login_required
def upload_image():
    try:
        # grab image name, filepath, username, caption
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        username = session[ "username" ]
        caption = request.form[ "caption" ]
        # if user checks allFollowers, set to true, else set false
        try:
            if request.form[ "allFollowers" ]:
                allFollowers = True
        except:
            allFollowers = False        
        # execute query to insert photo
        query = "INSERT INTO\
                Photo( photoOwner, timestamp, filePath, caption, allFollowers)\
                VALUES ( %s, %s, %s, %s, %s )"
        runQuery( query, None, (username, time.strftime('%Y-%m-%d %H:%M:%S'),\
                image_name, caption, allFollowers ) )
        # run query to grab photoID of the photo
        # that was last inserted (uploaded)
        query = "SELECT LAST_INSERT_ID()"
        data = runQuery( query, "one", None )
        photoID = data[ "LAST_INSERT_ID()" ]

        # if we're sharing the photo with our close friends group,
        if not allFollowers:
            # run query to grab all groups the current user is in
            query = "SELECT groupName, groupOwner\
                    FROM Belong\
                    WHERE username = %s"
            data = runQuery( query, "all", username )
            groupsAndOwners = [ ]
            # for every group ( and their corresponding owners ),
            # append groupName and groupOwner into a new array
            # array format is as follows:
            # [ [groupA_Name, groupA_Owner], 
            #   [groupB_Name, groupB_Owner], 
            # ... ]
            for element in data:
                groupsAndOwners.append( [ element[ "groupName" ], element[ "groupOwner" ] ] )
            # insert group names, group owners, and the photoID into 
            # the share table
            for groupOwner in groupsAndOwners:
                query = "INSERT INTO Share VALUES ( %s, %s, %s )"
                runQuery( query, None, ( groupOwner[ 0 ], groupOwner[ 1 ], photoID ) )
            message = "Image has been successfully uploaded and\
                    shared with your group"
        # else, if it is shared with just followers, 
        else:
            message = "Image has been successfully uploaded and\
                    shared with your followers"
        return render_template("upload.html", message=message)
    except:
        message = "Failed to upload image."
        return render_template("upload.html", message=message)


# list of groups the user is in page
# default value for errors is none ( if there are no errors )
@app.route( "/groups", methods=["GET"], defaults = {"error": None} )
@app.route( "/groups?<error>", methods=["GET"] )
@login_required
def groups( error ):
    # grab user's session and query to grab
    # groups user is in
    username = session["username"]
    currentGroupsQuery = "SELECT *\
                        FROM Belong\
                        WHERE username = %s"
    data = runQuery( currentGroupsQuery, "all", username )
    # if user is a member of something, print them out
    # else, return that there are no groups
    if data:
        if error:
            return render_template( "groups.html", error = error, data = data, username = username )
        return render_template( "groups.html", data = data, username = username )
    else:
        message = "you are not a member or owner of any group"
        if error:
            return render_template( "groups.html", error = error, message = message )
        return render_template( "groups.html", message = message )

# authenticating creation or joining
# a group
@app.route( "/groupsAuth", methods = ["POST"] )
@login_required
def groupAuth( ):
    # grab username and set error to none
    username = session["username"]
    error = None
    if request.form:
        # grab the group name and the option they chose
        groupName = request.form["groupName"]
        option = request.form["groupOption"]
        if option == "create":
            # SETTING CONSTRAINT THAT THERE CANNOT BE 
            # A SEMICOLON ; IN ANY GROUP NAME
            # THIS IS TO ALLOW FOR SEARCHING FOR 
            # GROUPS ALONG WITH THEIR OWNER
            if ";" in groupName:
                error = "You cannot have ';' in your group name"
            else:
                # try inserting user into belongs to and 
                # closefriendgroup, return error if fails
                try:
                    query = "INSERT INTO CloseFriendGroup VALUES ( %s, %s )"
                    runQuery( query, None, ( groupName, username ) )
                    query = "INSERT INTO Belong VALUES ( %s, %s, %s )"
                    runQuery( query, None, ( groupName, username, username ) )
                except pymysql.err.IntegrityError:
                    error = "You already own %s" %( groupName ) 
        elif option == "join":
            # CHECK TO SEE IF SEMICOLON IS PROVIDED,
            # RETURN ERROR IF NOT
            if ";" not in groupName:
                error = "You MUST have the format: <groupName>;<groupOwner>"
            else:
                # split to grab group name and owner
                info = groupName.split( ";" )
                groupName = info[0]
                groupOwner = info[1] 
                # if we cant find a corresponding pair of 
                # group name + owner, return empty set error
                query = "SELECT groupName, groupOwner\
                        FROM CloseFriendGroup NATURAL JOIN Belong\
                        WHERE groupName = %s AND groupOwner = %s"
                data = runQuery( query, "one", ( groupName, groupOwner ) )
                if not data:
                    error = "Either %s does not exist or %s\
                            does not own %s." %( groupName, groupOwner, groupName )
                else:
                    # try inserting, return error if user 
                    # is already member
                    try:
                        query = "INSERT INTO Belong VALUES ( %s, %s, %s )"
                        runQuery( query, None, ( groupName, groupOwner, username ) )
                    except pymysql.err.IntegrityError:
                        error = "You are already a member of %s" %( groupName ) 
        elif option == "leave":
            # check to see if the user owns the group.
            # if user does own the group, return an error
            # (owner cannot leave his own group)
            query = "SELECT groupName, groupOwner\
                    FROM CloseFriendGroup\
                    WHERE groupName = %s AND groupOwner = %s"
            data = runQuery( query, "one", ( groupName, username ) )
            if data:
                error = "You cannot leave %s as you are the owner" %( groupName )
            else:
                # remove user from group
                try:
                    query = "DELETE FROM Belong\
                            WHERE groupName = %s AND username = %s"
                    runQuery( query, None, ( groupName, username ) )
                # AS OF RIGHT NOW, THE NEXT TWO LINES WILL NOT RUN
                # THIS IS BECAUSE MYSQL WILL NOT RETURN AN ERROR IF:
                # A USER DOES NOT EXIST IN THE GROUP
                # OR
                # A GROUP DOES NOT EXIST
                except pymysql.err.IntegrityError:
                    error = "You are not a member of %s" %( groupName )
        else:  # option == "delete"
            # check if user is the owner of group
            # if user is not the owner, return an error
            query = "SELECT *\
                    FROM CloseFriendGroup\
                    WHERE groupName = %s AND groupOwner = %s"
            data = runQuery( query, "one", ( groupName, username ) )
            if not data:
                error = "You are not the owner of %s" %( groupName )
            # else, remove group and its corresponding members
            #  ( by using groupName and groupOwner )
            else:
                query = "DELETE FROM CloseFriendGroup WHERE \
                        groupName = %s AND groupOwner = %s"
                runQuery( query, None, ( groupName, username ) )
                query = "DELETE FROM Belong WHERE \
                        groupName = %s AND groupOwner = %s"
                runQuery( query, None, ( groupName, username ) )

    else:
        error = "An unknown error occurred. Please try again"
    return redirect( url_for( "groups", error = error ) )


# view your followers page
@app.route( "/follow", methods = ["GET"], defaults = {"error": None} )
@app.route( "/follow?<error>", methods = ["GET"] )
@login_required
def follow( error ):
    # grab username and option user selected (optional)
    currentUsername = session[ "username" ]
    option = request.args.get( "option" )
    followUsername = request.args.get( "username" )

    # if user accepts request, change bool to True
    if option == "accept":
        query = "UPDATE Follow\
                SET acceptedfollow = True\
                WHERE followerUsername = %s AND followeeUsername = %s"
        runQuery( query, None, ( followUsername, currentUsername ) )
    
    # if user declines, delete request
    if option == "reject":
        query = "DELETE FROM Follow\
                WHERE followerUsername = %s AND followeeUsername = %s"
        runQuery( query, None, ( followUsername, currentUsername ) )
    
    # if user unfollows someone, delete from follows
    if option == "unfollow":
        query = "DELETE FROM Follow\
                WHERE followerUsername = %s AND followeeUsername = %s"
        runQuery( query, None, ( currentUsername, followUsername ) )

    # run query to grab all follow requests
    # where followeeUsername = ourself AND we haven't accepted request
    query = "SELECT followerUsername\
            FROM Follow\
            WHERE followeeUsername = %s AND acceptedfollow = False"
    data = runQuery( query, "all", currentUsername )
    requests = [ ]
    for element in data:
        requests.append( element[ "followerUsername" ] ) 

    # run query to grab ALL WE FOLLOW ( we are follower ) 
    query = "SELECT followeeUsername\
            FROM Follow\
            WHERE followerUsername = %s AND acceptedfollow = True"
    data = runQuery( query, "all", currentUsername )
    followers = [ ]
    for element in data:
        followers.append( element[ "followeeUsername" ] )

    # run query to grab ALL FOLLOWEES ( we are followee )
    query = "SELECT followerUsername\
            FROM Follow\
            WHERE followeeUsername = %s AND acceptedfollow = True"
    data = runQuery( query, "all", currentUsername )
    followees = [ ]
    for element in data:
        followees.append( element[ "followerUsername" ] ) 
    return render_template( "follow.html", error = error,\
                        requests = requests, followers = followers,\
                        followees = followees )

# post method to grab entered username
# to follow
@app.route( "/followAuth", methods = ["POST"] )
@login_required
def followAuth( ):
    if request.form:
        # grab follower and followee
        followerUsername = session[ "username" ]
        followeeUsername = request.form[ "followeeUsername" ]
        # if someone wants to follow himself, return an error
        if followerUsername == followeeUsername: return redirect( url_for( "follow", error = "You cannot follow yourself" ) )
        # run query to check if user exists. if it doesn't, return error 
        query = "SELECT * FROM Person WHERE username = %s"
        data = runQuery( query, "one", followeeUsername )
        if not data:
            error = "%s does not exist" %( followeeUsername )             
            return redirect( url_for( "follow", error = error ) )
        # run query to add into follows. if request already exists,
        # return error
        try:
            query = "INSERT INTO Follow VALUES( %s, %s, %s )"
            runQuery( query, None, ( followerUsername, followeeUsername, False ) )
            error = "Request to %s has been sent" %( followeeUsername )
        except pymysql.err.IntegrityError:
            error = "Either you have already sent a request to\
                    or you already follow %s" %( followeeUsername )
        return redirect( url_for( "follow", error = error ) )
    else:
        error = "An error has occurred. Please try again"
        return redirect( url_for( "follow", error = error ) )


# post method to tag person into a photo
@app.route( "/tagPerson", methods = [ "POST" ] )
@login_required
def tagPerson( ):
    if request.form:
        # grab taggedUser's name ( from textfield )
        taggedUser = request.form[ "taggedUser" ]
        if len( taggedUser ) == 0: return redirect( url_for( "images", error = "you must enter a name" ) )\

        # run query to grab the photoID's owner
        photoID = request.args.get( "photoID" )
        query = "SELECT photoOwner\
                FROM photo\
                WHERE photoID = %s"
        photoOwner = runQuery( query, "one", photoID )[ "photoOwner" ]
        
        # check to see if either a request has been sent to tagUser
        # or if the user already accepted a tag request
        query = "SELECT *\
                FROM tag\
                WHERE photoID = %s AND username = %s"
        data = runQuery( query, "one", ( photoID, taggedUser ) )
        if data:
            error = "either a request to %s has already been sent or\
                    they are already tagged" %( taggedUser )
            return redirect( url_for( "images", error = error ) )

        # if we are the tagged user, add it to tag table
        if taggedUser == session[ "username" ]:
            query = "INSERT INTO Tag VALUES( %s, %s, True )"
            runQuery( query, None, ( taggedUser, photoID ) )
            error = "successfully tagged %s" %( taggedUser )
            return redirect( url_for( "images", error = error ) )

        # if the photoOwner is NOT the tagged user
        # NEEDED because the photoOwner cannot follow himself
        if photoOwner != taggedUser:
            # query to grab whether the photo is shared with followers or groups
            query = "SELECT allFollowers\
                    FROM photo\
                    WHERE photoID = %s"
            allFollowers = runQuery( query, "one", photoID )
            # if we're sharing with all followers,
            # check if the taggedUser is a follower of the current user
            if allFollowers["allFollowers"]:
                query = "SELECT *\
                        FROM follow\
                        WHERE followerUsername = %s AND followeeUsername = %s\
                            AND acceptedFollow = 1"
                data = runQuery( query, "one", ( taggedUser, photoOwner ) )
                # if taggedUser isn't a follower, return an error
                print( "1 ", data )
                if not data:
                    error = "you cannot tag %s as they do not follow %s" \
                            %( taggedUser, photoOwner )
                    return redirect( url_for( "images", error = error ) )
            
            # else, check to see if the taggedUser is in the same group
            # as the current user
            else:
                query = "SELECT *\
                        FROM belong AS b1 JOIN belong AS b2 USING( groupName, groupOwner )\
                        WHERE b1.username = %s AND b2.username = %s"
                data = runQuery( query, "one", ( taggedUser, photoOwner ) )
                # if taggedUser isn't a follower, return an error
                print( "2", data )
                if not data:
                    error = "you cannot tag %s as they are not in the same group\
                            as %s" %( taggedUser, photoOwner )
                    return redirect( url_for( "images", error = error ) )
                
        # try inserting the tag into the tag table. if there is an error,
        # that means there already is a tagged request for the user 
        query = "INSERT INTO Tag VALUES( %s, %s, False )"
        runQuery( query, None, ( taggedUser, photoID ) )
        error = "tag request has been sent to %s" %( taggedUser )
        return redirect( url_for( "images", error = error ) )
    # if user didn't submit form, return error
    error = "something went wrong. please try again"
    return redirect( url_for( "images", error = error ) )




if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()
