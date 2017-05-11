from flask import Flask, render_template, make_response, redirect, request
import pymysql, json, requests, string, random, datetime
import ssl, logging

with open("config.json", "r") as f:
    config = json.load(f)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

connection = pymysql.connect(host=config['host'], user=config['user'], passwd=config['password'], db=config['database'], charset='utf8')
connection.autocommit(True)
cursor = connection.cursor(pymysql.cursors.DictCursor)

app = Flask(__name__)

def execute(sql, args=None):
    global connection
    global cursor
    try:
        cursor.execute(sql, args) if args is not None else cursor.execute(sql)
        return cursor
    except pymysql.err.OperationalError:
        connection.connect()
        return execute(sql, args)

def checker(username=None, api=None):
    if username == None:
        execute("SELECT * FROM users WHERE api=%s", [api])
    else:
        execute("SELECT * FROM users WHERE username=%s", [username])
    counter = cursor.fetchone()
    if counter != None and len(counter) > 0:
        return True
    else:
        return False

def counter(id):
    arr = []
    # Pending
    count = {}
    q = execute("SELECT COUNT(action) as c FROM requests WHERE user_id = %s AND action=0", [id])
    results = q.fetchone()
    count["pending"] = str(results["c"])
    arr.append(count)
    # Played
    count = {}
    q = execute("SELECT COUNT(action) as c FROM requests WHERE user_id = %s AND action=1", [id])
    results = q.fetchone()
    count["played"] = str(results["c"])
    arr.append(count)
    # Ignored
    count = {}
    q = execute("SELECT COUNT(action) as c FROM requests WHERE user_id = %s AND action=2", [id])
    results = q.fetchone()
    count["ignored"] = str(results["c"])
    arr.append(count)
    # Total
    count = {}
    q = execute("SELECT COUNT(action) as c FROM requests WHERE user_id = %s", [id])
    results = q.fetchone()
    count["total"] = str(results["c"])
    arr.append(count)
    # Status
    count = {}
    q = execute("SELECT bot, username FROM users WHERE id = %s", [id])
    results = q.fetchone()
    count["status"] = str(results["bot"])
    count["username"] = str(results["username"])
    arr.append(count)
    return arr

@app.route('/')
@app.route('/<where>/')
def index(where='0'):
    api = request.cookies.get('api')
    list_requests = []
    ca = ''
    if checker(api=api) == True:
        q = execute("SELECT * FROM users WHERE api=%s", [api])
        result = q.fetchone()
        info = result
        temp_request = {}
        res = execute("SELECT * FROM requests WHERE user_id = %s and action = %s ORDER BY id and action = 0 desc", [info["id"], where])
        results = res.fetchall()
        for row in results:
            temp_request["id"] = row["id"]
            temp_request["user_id"] = row["user_id"]
            temp_request["requested_by"] = row["requested_by"]
            temp_request["song_id"] = row["song_id"]
            temp_request["title"] = row["title"]
            temp_request["duration"] = row["duration"].split('PT')[1].lower()
            temp_request["mode"] = row["mode"]
            temp_request["status"] = row["status"]
            temp_request["action"] = row["action"]
            list_requests.append(temp_request)
            temp_request = {}
        ca = counter(info["id"])
    else:
        info = None
        
    return render_template('index.html', path=request.url_root, url=request.url, userinfo=info, list_requests=list_requests, where=where, stats=ca)

@app.route('/action/<action>/')
@app.route('/action/<action>/<rid>')
def action_delete(action, rid = None):
    api = request.cookies.get('api')
    q = execute("SELECT * FROM users WHERE api=%s", [api])
    result = q.fetchone()
    if action == "done":
        execute("UPDATE requests SET action=1 WHERE user_id = %s and id = %s", [result["id"], rid])
        execute("UPDATE requests SET status=0 WHERE user_id = %s and id = %s", [result["id"], rid])
    elif action == "ignore":
        execute("UPDATE requests SET action=2 WHERE user_id = %s and id = %s", [result["id"], rid])
        execute("UPDATE requests SET status=0 WHERE user_id = %s and id = %s", [result["id"], rid])
    elif action == "delete":
        execute("DELETE FROM requests WHERE user_id = %s and id = %s", [result["id"], rid])
    elif action == "playing":
        execute("UPDATE requests SET status=1 WHERE user_id = %s and id = %s", [result["id"], rid])
    elif action == "bot":
        if result["bot"] == 1:
            execute("UPDATE users SET bot=0 WHERE id = %s", [result["id"]])
        else:
            execute("UPDATE users SET bot=1 WHERE id = %s", [result["id"]])
    red = make_response(redirect('/'))
    return red

@app.route('/twitch/')
def twitch():
    code = request.args['code']
    meme = {'client_id' : config["twitch_client"], 'client_secret' : config["twitch_secret"], 'grant_type' : 'authorization_code', 'redirect_uri' : 'https://as2.aiaegames.xyz/twitch/', 'code' : code}
    twitch_api = requests.post("https://api.twitch.tv/kraken/oauth2/token", data=meme).json()
    headers = {'Authorization' : 'OAuth ' + twitch_api['access_token']}
    user = requests.get('https://api.twitch.tv/kraken/', headers=headers).json()
    if checker(user["token"]["user_name"]):
        q = execute("SELECT * FROM users WHERE username=%s", [user["token"]["user_name"]])
        result = q.fetchone()
        key = result["api"]
    else:
        key = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(20))
        execute("INSERT INTO users (username, api) VALUES(%s, %s)", [user["token"]["user_name"], key])
    expire_date = datetime.datetime.now()
    expire_date = expire_date + datetime.timedelta(days=90)
    red = make_response(redirect('/'))
    red.set_cookie('api', key, expires=expire_date)
    return red

@app.route('/playing/<username>/')
def playing(username):
    q = execute("SELECT id FROM users WHERE username=%s", [username])
    result = q.fetchone()
    q = execute("SELECT * FROM requests WHERE status=1 and user_id=%s", [result["id"]])
    result = q.fetchone()
    if result == None:
        return render_template('playing.html', path=request.url_root, url=request.url, text="")
    text = "Current song length {} requested by {}".format(result["duration"].split('PT')[1].lower(), result["requested_by"])
    return render_template('playing.html', path=request.url_root, url=request.url, text=text)

@app.errorhandler(404)
def not_found(error):
    red = make_response(redirect('/'))
    return red

if __name__ == "__main__":
    context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
    context.load_cert_chain('host.crt', 'aiae.key')

    app.run(debug=True, port=7294, ssl_context=context, threaded=False, host='0.0.0.0')