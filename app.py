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
@app.route("/images", methods=["GET"])
@login_required
def images():
    # set and execute query to get all photos
    query = "SELECT * FROM photo"
    with connection.cursor() as cursor:
        cursor.execute(query)
    # fetch data and pass into images page
    data = cursor.fetchall()
    return render_template("images.html", images=data)

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
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        # hash password to compare with hashed stored in database
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()

        # execute query to find corresponding username and password
        with connection.cursor() as cursor:
            query = "SELECT * FROM person WHERE username = %s AND password = %s"
            cursor.execute(query, (username, hashedPassword))
        data = cursor.fetchone()

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
        requestData = request.form
        username = requestData["username"]
        plaintextPasword = requestData["password"]
        hashedPassword = hashlib.sha256(plaintextPasword.encode("utf-8")).hexdigest()
        firstName = requestData["fname"]
        lastName = requestData["lname"]
        
        # execute query: if username exists, return an error
        # else, add to database and redirect to login 
        try:
            with connection.cursor() as cursor:
                query = "INSERT INTO person (username, password, fname, lname) VALUES (%s, %s, %s, %s)"
                cursor.execute(query, (username, hashedPassword, firstName, lastName))
        except pymysql.err.IntegrityError:
            error = "%s is already taken." % (username)
            return render_template('register.html', error=error)    

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
    if request.files:
        # grab image name, filepath
        image_file = request.files.get("imageToUpload", "")
        image_name = image_file.filename
        filepath = os.path.join(IMAGES_DIR, image_name)
        image_file.save(filepath)
        # execute query to insert the photo's timestamp and filepath
        query = "INSERT INTO photo (timestamp, filePath) VALUES (%s, %s)"
        with connection.cursor() as cursor:
            cursor.execute(query, (time.strftime('%Y-%m-%d %H:%M:%S'), image_name))
        message = "Image has been successfully uploaded."
        return render_template("upload.html", message=message)
    else:
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
    currentGroupsQuery = "SELECT * FROM Belong WHERE username = %s"
    with connection.cursor( ) as cursor:
        cursor.execute( currentGroupsQuery, username )
    data = cursor.fetchall( )
    # if user is a member of something, print them out
    # else, return that there are no groups
    if data:
        if error is not None:
            return render_template( "groups.html", error = error, data = data, username = username )
        return render_template( "groups.html", data = data, username = username )
    else:
        message = "you are not a member or owner of any group"
        if error is not None:
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
        requestData = request.form
        groupName = requestData["groupName"]
        option = requestData["groupOption"]
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
                    with connection.cursor() as cursor:
                        query = "INSERT INTO CloseFriendGroup VALUES ( %s, %s )"
                        cursor.execute( query, ( groupName, username ) )
                        query = "INSERT INTO Belong VALUES ( %s, %s, %s )"
                        cursor.execute( query, ( groupName, username, username ) )
                except pymysql.err.IntegrityError:
                    error = "You already own %s" % ( groupName ) 
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
                with connection.cursor( ) as cursor:
                    subQuery = "SELECT groupName, groupOwner FROM CloseFriendGroup\
                            NATURAL JOIN Belong WHERE groupName = %s AND groupOwner = %s"
                    cursor.execute( subQuery, ( groupName, groupOwner ) )
                data = cursor.fetchone( )
                if not data:
                    error = "Either the group does not exist or the owner\
                        specified does not own the group."
                else:
                    # try inserting, return error if user 
                    # is already member
                    try:
                        with connection.cursor( ) as cursor:
                            query = "INSERT INTO Belong VALUES ( %s, %s, %s )"
                            cursor.execute( query, ( groupName, groupOwner, username ) )
                    except pymysql.err.IntegrityError:
                        error = "You are already a member of %s" % ( groupName ) 
        elif option == "leave":
            # check to see if the user owns the group.
            # if user does own the group, return an error
            # (owner cannot leave his own group)
            with connection.cursor( ) as cursor:
                subQuery = "SELECT groupName, groupOwner FROM CloseFriendGroup\
                            WHERE groupName = %s AND groupOwner = %s"
                cursor.execute( subQuery, ( groupName, username ) )
                data = cursor.fetchone( )
            if data:
                error = "You cannot leave a group you are the owner of"
            else:
                # remove user from group
                try:
                    query = "DELETE FROM Belong WHERE groupName = %s AND \
                            username = %s"
                    with connection.cursor( ) as cursor:
                        cursor.execute( query, ( groupName, username ) )
                # AS OF RIGHT NOW, THE NEXT TWO LINES WILL NOT RUN
                # THIS IS BECAUSE MYSQL WILL NOT RETURN AN ERROR IF
                # A USER DOES NOT EXIST IN THE GROUP
                # OR
                # A GROUP DOES NOT EXIST
                except pymysql.err.IntegrityError:
                    error = "You are not a member of the group"
    else:
        error = "An unknown error occurred. Please try again"
    return redirect( url_for( "groups", error = error ) )


if __name__ == "__main__":
    if not os.path.isdir("images"):
        os.mkdir(IMAGES_DIR)
    app.run()
