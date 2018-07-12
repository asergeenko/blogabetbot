# -*- coding: utf-8 -*-
import os

import telebot
from flask import Flask, request
import psycopg2

import time
import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from lxml import html
import requests
from requests import Session

TOKEN = 'Telegram bot token'
bot = telebot.TeleBot(TOKEN)
DATABASE_URL = 'Database url'
server = Flask(__name__)
scheduler = BackgroundScheduler()
atexit.register(lambda: scheduler.shutdown())

@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(message.chat.id, 'Available commands:\n/add [tipster_name] - add new tipster\n/remove [tipster_name] - remove tipster\n/list - show tipsters list')
@bot.message_handler(commands=['list'])
def list_tipsters(message):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT tipsters.urlname FROM tipsters,chats_tipsters WHERE tipsters.tipster_id=chats_tipsters.tipster_id AND chats_tipsters.chat_id=%s;", (message.chat.id,))
    if cursor.rowcount==0:
        bot.send_message(message.chat.id,'Your tipsters list is empty. You can add one by typing\n/add [tipster_name]')
    else:
        bot.send_message(message.chat.id, '\n'.join([item[0] for item in cursor.fetchall()]))
    cursor.close()
    conn.close()

@bot.message_handler(commands=['remove'])
def remove(message):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    st = message.text.split(' ')
    if len(st)!=2:
        bot.send_message(message.chat.id,"Type /remove [tipster_name] to remove tipster.")
        return
    urlname = st[1]
    cursor.execute("SELECT tipster_id FROM tipsters where urlname=%s;",(urlname,))
    if cursor.rowcount==0:
        bot.send_message(message.chat.id,"Tipster *"+urlname+"* doesn't exist in your list.",parse_mode="Markdown")
    else:
        tipster_id = cursor.fetchone()[0]
        cursor.execute("DELETE FROM chats_tipsters WHERE chats_tipsters.tipster_id=%s AND chats_tipsters.chat_id=%s;", (tipster_id,message.chat.id,))
        conn.commit()
        bot.send_message(message.chat.id, "Tipster *" + urlname + "* successfully removed from the list.", parse_mode="Markdown")
    cursor.close()
    conn.close()

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Hello, ' + message.from_user.first_name + '. I will send you new tips from specified tipsters from blogabet.com. Type /help to see available commands.')
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO chats_info(chat_id) values(%s);",(message.chat.id,))
    conn.commit()
    cursor.close()
    conn.close()

@bot.message_handler(commands=['add'])
def add_tipster(message):
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    st = message.text.split(' ')
    if len(st)!=2:
        bot.send_message(message.chat.id,"Type /add [tipster_name] to add a new tipster.")
        return
    urlname = st[1]
    cursor.execute("SELECT * FROM tipsters where urlname=%s;",(urlname,))
    msg=''
    tipster_id = -1
    if cursor.rowcount==0:
        response = requests.get('https://'+urlname+'.blogabet.com/')
        tree = html.fromstring(response.text)
        if tree.xpath("/html/head/title")[0].text.startswith('Blog not found'):
            bot.send_message(message.chat.id, 'Can\'t add tipster *'+urlname+'*. Website https://'+urlname+'.blogabet.com/ does not exist.',parse_mode='Markdown',disable_web_page_preview=True)
            return
        else:
            cursor.execute("INSERT INTO tipsters(urlname) VALUES(%s) RETURNING tipster_id;",(urlname,))
            conn.commit()
            tipster_id = cursor.fetchone()[0]
            lst = get_tips_from_tipster(urlname)
            for li in lst:
                cursor.execute("INSERT INTO tips(tipster_id,date_time) VALUES(%s,%s)",(tipster_id,li.attrib["data-time"]))
            conn.commit()
    else:
        tipster_id = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM chats_tipsters WHERE chat_id=%s AND tipster_id=%s;",(message.chat.id,tipster_id))
    if int(cursor.fetchone()[0])>0:
        msg+="Tipster *"+urlname+"* is already in your list."
    else:
        cursor.execute("INSERT INTO chats_tipsters(chat_id,tipster_id) VALUES(%s,%s);", (message.chat.id,tipster_id))
        conn.commit()
        msg += "Tipster *" + urlname + "* succesfully added."

    bot.send_message(message.chat.id, msg,parse_mode='Markdown')
    cursor.close()
    conn.close()

@server.route('/' + TOKEN, methods=['POST'])
def getMessage():
    bot.process_new_updates([telebot.types.Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@server.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url='https://blogabetbot.herokuapp.com/' + TOKEN)
    return "!", 200
def get_tips_from_tipster(urlname):
    session = Session()
    SOURCE_SITE_URL = 'https://' + urlname + '.blogabet.com/blog/dashboard'
    session.head(SOURCE_SITE_URL)
    response = session.get(
        SOURCE_SITE_URL,
        headers={'Referer': 'https://' + urlname + '.blogabet.com/',
                 'Accept-Encoding': 'gzip, deflate, br',
                 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.87 Safari/537.36',
                 'Cookie': '_ga=GA1.2.1871104935.1529094724; __gads=ID=6ec2f53ceaeb39ff:T=1529137002:S=ALNI_Mao_o9pHbKzQ9jPdq8_B3kdocSMDQ; cookiesDirective=1; _gid=GA1.2.1161230770.1530264484; login_string=37c1a601e9e336eca1d3c7244ed256a631e7c8f0f90a806600c2e3e007764154a56190e191d70bdf3be4ea55df7757ea1838ad2ad836a76a26bc843fcd1b5904; remember_me=1; __atuvc=1%7C26; __atuvs=5b35ff9712464bd9000',
                 'X-Compress': 'null',
                 'X-Requested-With': 'XMLHttpRequest',
                 'Connection': 'keep-alive'
                 })
    tree = html.fromstring(response.text)
    return tree.xpath(".//div[@id='_blogPostsContent']/ul/ul/li")

def check_new_tips():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tipsters;")
    for tipster in cursor.fetchall():
        lst = get_tips_from_tipster(tipster[1])
        for li in lst:
            cursor.execute("SELECT (tip_id,date_time) FROM tips WHERE tipster_id=%s AND date_time=%s;",(tipster[0],li.attrib["data-time"]))
            if cursor.rowcount==0:
                cursor.execute("INSERT INTO tips(tipster_id,date_time) VALUES(%s,%s);",(tipster[0],li.attrib["data-time"]))   
                conn.commit()
                tip = li.xpath("div/div[@class='feed-pick-title']/div[1]")[0]
                msg='New tip from *'+tipster[1]+'*\n'
                msg+='['+tip.xpath("h3/a")[0].text+']('+tip.xpath("h3/a/@href")[0]+')\n'
                labels = tip.xpath("div[@class='labels']")[0]
                msg+=labels.xpath("span")[0].text+' ['+labels.xpath("a")[0].text+']('+labels.xpath("a/@href")[0]+')\n'
                pick_line = tip.xpath("div[@class='pick-line']")[0]
                msg+=' '.join(pick_line.text.split())+' '+pick_line.xpath("span")[0].text+'\n'
                sport_line = tip.xpath("div[@class='sport-line']/small/span")
                for b in sport_line:
                    msg+=b.text+b.tail.replace('\n','').rstrip(' ')+'\n'
                cursor.execute("SELECT chat_id FROM chats_tipsters WHERE tipster_id=%s;",(tipster[0],))
                for chat_id in cursor.fetchall():
                    bot.send_message(chat_id[0],msg,parse_mode="Markdown",disable_web_page_preview=True)
    cursor.close()
    conn.close()
if __name__ == "__main__":
    scheduler.start()
    scheduler.add_job(func=check_new_tips,trigger=IntervalTrigger(seconds=50),id='check_new_tips',name='Checking for new tips',replace_existing=True)
    server.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))



