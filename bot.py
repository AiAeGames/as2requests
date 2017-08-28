#!/usr/bin/env python
# -*- coding: utf-8 -*-

import irc.bot
import irc.strings
import json, time, re, pymysql, requests
from cooldown import cooldown
from threading import Thread
from datadog import statsd

with open("config.json", "r") as f:
    config = json.load(f)

def connect():
    connection = pymysql.connect(host=config['host'], user=config['user'], passwd=config['password'], db=config['database'], charset='utf8')
    connection.autocommit(True)
    cursor = connection.cursor(pymysql.cursors.DictCursor)
    return connection, cursor

def execute(connection, cursor, sql, args=None):
    try:
        cursor.execute(sql, args) if args is not None else cursor.execute(sql)
        return cursor
    except pymysql.err.OperationalError:
        print ("Something went wrong with mysql connection.... trying to reconnect.")
        connection.connect()
        return execute(sql, args)

def youtube_api(v):
    try:
        request = requests.get("https://www.googleapis.com/youtube/v3/videos?id={}&part=snippet,contentDetails&key={}&fields=items(snippet/title,contentDetails/duration)".format(v, config["youtube_api"]))
        return json.loads(request.text)
    except requests.exceptions.RequestException as e:
        return

class Reconnect(irc.bot.ReconnectStrategy):
    def run(self, bot):
        if not bot.connection.is_connected():
            print("Trying to reconnect...")
            bot.jump_server()

class TwitchBot(irc.bot.SingleServerIRCBot):
    connection, cursor = connect()
    def __init__(self):
        irc.bot.SingleServerIRCBot.__init__(self, [(config["twitch_irc"], 6667, config["twitch_oauth"])], config["twitch_username"], config["twitch_username"], recon=Reconnect())

    def on_pubmsg(self, c, e):
        self.do_command(e)
        #print(e)

    @cooldown(20)
    def youtube_request(self, groups, e):
        statsd.increment('as2.new_request')
        link, v, mode = groups
        channel = e.target
        user_quarry = execute(self.connection, self.cursor, "SELECT id FROM users WHERE username = %s", [channel.replace("#", "")])
        user_result = user_quarry.fetchone()
        if mode == None or mode == "":
            mode = 'not specified'
        yt = youtube_api(v)
        title = yt["items"][0]["snippet"]["title"]
        duration = yt["items"][0]["contentDetails"]["duration"]
        request_quarry = execute(self.connection, self.cursor, "INSERT INTO requests (user_id, requested_by, song_id, title, duration, mode, action) VALUES(%s, %s, %s, %s, %s, %s, %s)", [user_result["id"], e.source.nick, v, title, duration, mode, 0])
        msg = '{} is added.'.format(title)
        self.connection.privmsg(channel, msg)

    def do_command(self, e):
        c = self.connection
        message = e.arguments[0]
        regexes = [
            ('(?:https?:\/\/)?(?:www\.)?youtu(.be\/|be\.com\/watch\?v=)([a-zA-Z0-9_.-]*)?(.*)', self.youtube_request),
        ]

        for regex in regexes:
            reg = re.match(regex[0], message)
            if reg:
                regex[1](reg.groups(), e)

bot = TwitchBot()
Thread(target=bot.start).start()

time.sleep(5)

def AutoJoin(mtbot):
    connection, cursor = connect()
    channels = []
    while True:
        quarry = execute(connection, cursor, "SELECT username, bot FROM users")
        twitch_users = quarry.fetchall()
        for row in twitch_users:
            if row["username"] not in channels and row["bot"] == 1:
                print("Join " + row["username"])
                channels.append(row["username"])
                mtbot.connection.join("#" + row["username"])
            elif row["bot"] == 0 and row["username"] in channels:
                print("Part " + row["username"])
                channels.remove(row["username"])
                mtbot.connection.part("#" + row["username"])
        time.sleep(60)

Thread(target=AutoJoin, args=(bot, )).start()