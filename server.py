""" Volunteer app server. """

from jinja2 import StrictUndefined

from flask import Flask, render_template, redirect, request, flash, session
from flask_debugtoolbar import DebugToolbarExtension

from model import Volunteer, Organization, Category, OrganizationVolunteer, connect_to_db, db

from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import os

# set up twilio client
account_sid = os.environ['ACCOUNT_SID']
auth_token = os.environ['AUTH_TOKEN']
client = Client(account_sid, auth_token)

# set up flask app
app = Flask(__name__)
app.secret_key = 'abc'

# Make sure Jinja raises errors
app.jinja_env.undefined = StrictUndefined


###################### LANDING AND GENERAL LOGIN ######################
@app.route("/")
def show_landing():
    """Landing page"""
    return render_template('landing.html')


@app.route("/login")
def show_login():
    """Login option for volunteers or organizations"""
    return render_template('login.html')


###################### REGISTER / LOGIN FOR VOLUNTEERS #####################
@app.route('/register/volunteer', methods=['GET'])
def show_volunteer_register_form():
    """Shows registration form to volunteer"""
    return render_template('register-volunteer.html')


@app.route('/register/volunteer', methods=['POST'])
def process_volunteer_register_form():
    """ Process data given by user in form and add to database."""

    name = request.form.get('name')
    email = request.form.get('email')
    phone_number = request.form.get('phone_number')
    password = request.form.get('password')

    volunteer = Volunteer(name=name, email=email, phone_number=phone_number, password=password)
    db.session.add(volunteer)
    db.session.commit()

    flash('Thanks for registering. Please login.')
    return redirect('/login/volunteer')


@app.route('/login/volunteer', methods=['GET'])
def show_volunteer_login():
    """Shows form for volunteer to sign in."""
    return render_template('login-volunteer.html')


@app.route('/login/volunteer', methods=['POST'])
def verify_volunteer_login():
    """Verifies volunteer's email is in database and password matches"""

    # gets email and password from form and verifies user in db
    email = request.form.get('email')
    password = request.form.get('password')
    volunteer = Volunteer.query.filter(Volunteer.email == email).first()

    # if user doesn't exist, redirect
    if not volunteer:
        flash('No user exists with that email address.')
        return redirect('/login/volunteer')

    # if user exists but passwords don't match
    if volunteer.password != password:
        flash('Incorrect password for the email address entered.')
        return redirect('/login/volunteer')

    # add user_id to session
    session['user_id'] = volunteer.volunteer_id
    session['type'] = 'volunteer'

    # redirect to home page
    flash('You are now logged in.')
    return redirect('/home')


###################### REGISTER / LOGIN FOR ORGANIZATIONS #####################
@app.route('/register/organization', methods=['GET'])
def show_registration_form():
    """Shows registration form to user"""

    return render_template('register-org.html')


@app.route('/register/organization', methods=['POST'])
def show_org_registration_form():
    """Shows registration form to organization"""

    name = request.form.get('name')
    email = request.form.get('email')
    password = request.form.get('password')
    address = request.form.get('address')
    category = request.form.get('category')
    description = request.form.get('description')
    website = request.form.get('website')

    organization = Organization(name=name, email=email, password=password,
                                address=address, category=category,
                                description=description, website=website)

    db.session.add(organization)
    db.session.commit()

    flash('Thanks for registering. Please login.')
    return redirect('/login/organization')


@app.route('/login/organization', methods=['GET'])
def show_organization_login():
    """Shows form for organization to sign in."""
    return render_template('login-org.html')


@app.route('/login/organization', methods=['POST'])
def verify_organization_login():
    """Verifies org email is in database and password matches"""

    # gets email and password from form and verifies user in db
    email = request.form.get('email')
    password = request.form.get('password')
    organization = Organization.query.filter(Organization.email == email).first()

    # if user doesn't exist, redirect
    if not organization:
        flash('No organization exists with that email address.')
        return redirect('/login/organization')

    # if user exists but passwords don't match
    if organization.password != password:
        flash('Incorrect password for the email address entered.')
        return redirect('/login/organization')

    # add user_id to session
    session['user_id'] = organization.organization_id
    session['type'] = 'organization'

    # redirect to home page
    flash('You are now logged in.')
    return redirect('/home')


##################### ORGANIZATION ALERT CREATION ######################
@app.route('/create-alert', methods=['GET'])
def show_alert_form():
    """Shows form to create alert for an organization"""

    if session['type'] != 'organization':
        return redirect('/home')
    else:
        return render_template('create-alert.html')


@app.route('/create-alert', methods=['POST'])
def process_alert():
    """Get data from form and return template for user review."""

    if session['type'] != 'organization':
        return redirect('/home')
    else:
        # find organization and grab all people interested in it
        org_id = session['user_id']
        org = Organization.query.filter(Organization.organization_id == org_id).first()
        volunteers = org.retrieve_volunteers()
        phone_numbers = []

        for volunteer in volunteers:
            phone_numbers.append(volunteer.phone_number)

        num_volunteers = request.form.get('num_volunteers')
        day = request.form.get('day')
        hours = request.form.get('hours')
        ampm = request.form.get('ampm')
        time = hours + " " + ampm

        message = "Helper request: {} needs {} volunteers {} at {}. Can you help? Reply YES.".format(org.name,
                                                                                          num_volunteers,
                                                                                          day,
                                                                                          time)

        sms_volunteer_request(phone_numbers, message)
        # return render_template('/sms', message=message, phone_numbers=phone_numbers)
        return redirect('/home')
        # on this template users review the alert
        # if they like it, it connects to the twilio '/sms' route below
        # need to figure out how to pass in the phone numbers on that route...
        # if not, they are redirected back to the '/create-alert' route


##################### GENERAL PAGES ######################
@app.route('/home')
def show_homepage():
    """ Show user / org details """

    if session['type'] == 'volunteer':
        volunteer = Volunteer.query.get(session['user_id'])
        organizations = volunteer.retrieve_organizations_volunteer_is_in()

        pass
    elif session['type'] == 'organization':
        # show organization details, any current alerts, link to create an alert
        organization = Organization.query.get(session['user_id'])
        volunteers = organization.retrieve_volunteers()
        return render_template('homepage.html', organization=organization, volunteers=volunteers)
    else:
        return redirect('/landing')


@app.route("/logout")
def logout():
    """Logs the current user out"""

    # remove session from browser to log out
    del session['user_id']
    del session['type']
    flash('Logged out.')
    return redirect("/")


#################### TWILIO SMS ROUTES ####################
# @app.route("/sms")
def sms_volunteer_request(phone_numbers, message):
    """Connects organizations on our app to the Twilio functionality."""

    if session['type'] != 'organization':
        return redirect('/home')

    for num in phone_numbers:
        call = client.messages.create(to=num, from_='+15109441564', body=message,)
        print(call.sid)

    flash("Your request for volunteers was sent!")
    # return redirect("/home")


@app.route("/sms", methods=['GET', 'POST'])
def sms_reply_attending_():
    """Respond to incoming messages that way the volunteer will attend
    with an SMS containing more data."""

    # Start our response
    resp = MessagingResponse()

    # Add a message
    resp.message("Can't wait to see you! Find more info at helper.com.")

    return str(resp)


if __name__ == '__main__':
    # Activate debug mode
    # app.debug = True

    # make sure templates, etc. are not cached in debug mode
    # app.jinja_env.auto_reload = app.debug

    connect_to_db(app)

    # Use the DebugToolbar
    # DebugToolbarExtension(app)

    app.run(port=5000, host='0.0.0.0')



































