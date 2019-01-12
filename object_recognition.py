# coding=UTF-8
import tensorflow as tf
import MySQLdb
import speech_recognition
import jieba
import sys
import time
import threading
from pygame import mixer
from gtts import gTTS
import picamera
from picamera.array import PiRGBArray
import random
import json
import socket
import pygame
import os
import cv2
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw

reload(sys)
sys.setdefaultencoding('utf-8')

def init_loading():
    global label_lines
    print("Loading labels...")
   
    label_lines = [line.rstrip() for line 
                       in tf.gfile.GFile("/home/pi/work/src/object_labels.txt")]
    print("Loading graph...")
    # Unpersists graph from file
    with tf.gfile.FastGFile("/home/pi/work/src/object_graph.pb", 'rb') as f:
        graph_def = tf.GraphDef()   
        graph_def.ParseFromString(f.read())     
        _ = tf.import_graph_def(graph_def, name='') 
    

def recognize_image():
    global label_lines, cursor
    image_path = 'capture_image.jpg'
    time1 = time.time()
    print("Loading image...")
    # Read in the image_data
    image_data = tf.gfile.FastGFile(image_path, 'rb').read()
    with tf.Session() as sess:
        
        softmax_tensor = sess.graph.get_tensor_by_name('final_result:0')

        
        predictions = sess.run(softmax_tensor, \
                 {'DecodeJpeg/contents:0': image_data})       
        
        
        top_k = predictions[0].argsort()[-len(predictions[0]):][::-1]

        # for node_id in top_k:
        #     object_string = label_lines[node_id]
        #     score = predictions[0][node_id]
        #     print('%s (score = %.5f)' % (object_string, score))
        object_string = label_lines[top_k[0]]
        score = predictions[0][top_k[0]]
        print('%s (score = %.5f)' % (object_string, score))
        time2 = time.time()
        print('辨識花費時間 : %.2f s' % (time2 - time1))
        if score < 0.5 :
            return 'nothing'
        cursor.execute("SELECT chinese_name FROM commodity WHERE english_name = %s", (label_lines[top_k[0]]))
        results = cursor.fetchall()
        results = results[0][0].encode('utf-8')       
        return results

def bot_reply(robot_reply):
    global x, lock, is_speaking
    save_subtitle(robot_reply)
    is_speaking = True
    lock.acquire()
    if x== 0 :
        sound_path = 'sound0.mp3'
        x=1
    else :
        sound_path = 'sound1.mp3'
        x=0
    tts = gTTS(text = robot_reply,lang='zh')
    tts.save(sound_path)
    mixer.init()
    mixer.music.load(sound_path)
    mixer.music.play()
    print('robot: ' + robot_reply)
    while mixer.music.get_busy():
        pass
    mixer.music.stop()
    print('播放結束')
    lock.release()
    is_speaking = False

def user_speak():
    global nobody_count, is_time_couting
    user_request=''
    print"user: ",
    r = speech_recognition.Recognizer()

    with speech_recognition.Microphone(device_index=2, chunk_size = 512) as source:
        try:
            r.adjust_for_ambient_noise(source, duration = 1)
            audio = ''
            print 'recording...'
            audio = r.listen(source, timeout = 5)
        except speech_recognition.WaitTimeoutError:
            print 'speech_recognition.WaitTimeout'
            nobody_count = nobody_count + 1
        try:
            if audio is not '':
                print 'recognizing...'
                user_request = r.recognize_google(audio ,language='zh_tw')
                nobody_count = 0
        except speech_recognition.UnknownValueError:
            print("speech_recognition.UnknownValue")
            nobody_count = nobody_count + 1

    print(user_request)
    is_time_couting = False
    return user_request

def analysis_sentence(user_request):
    global cursor
    max_weight = 0
    if(user_request!=''): #判斷user是否有講話
        cursor.execute("SELECT reply FROM conversation WHERE request_keyword = %s", (user_request))
        results = cursor.fetchall()
        if results:                 #找到db內有此句子的回答方式
            robot_reply = results[0][0].encode('utf-8') 
            isFound_reply=1
        else:                       #沒找到整句，將進行斷句
            seg_list = jieba.cut(user_request)  #將句子斷詞，用關鍵字方式查詢
            request_list = list(seg_list)   #將斷詞的集合轉為list型態
            isFound_reply=0
            for seg_word in request_list:
                #print(seg_word.encode('utf-8'))
                keyword = seg_word.encode('utf-8')
                cursor.execute("SELECT weight FROM conversation WHERE request_keyword = %s", (keyword))
                results = cursor.fetchall()
                if not results: #若沒找到權重繼續找
                    continue
                else:   #若找到權重，isFound_reply=1 代表已找到合適的回答
                    if results[0][0] > max_weight:
                        max_weight = results[0][0]
                        cursor.execute("SELECT reply FROM conversation WHERE request_keyword = %s", (keyword))
                        results = cursor.fetchall()
                        robot_reply = results[0][0].encode('utf-8')
                        isFound_reply=1
                    
            if isFound_reply == 0:  #利用斷詞過後的關鍵字也找不到回答句子
                if user_request.find("為什麼")>=0 or user_request.find("嗎")>=0 or user_request.find("請問")>=0: #判斷是否問句
                    robot_reply = '對於你的疑問，我不知道該回答什麼'
                else:
                    cursor.execute("SELECT COUNT(id) FROM others") #計算others有多少句子
                    results = cursor.fetchall()
                    total_count = results[0][0]
                    random_num = random.randint(1,total_count) #隨機取一句
                    cursor.execute("SELECT reply FROM others WHERE id = %s", (random_num))
                    results = cursor.fetchall()
                    robot_reply = results[0][0].encode('utf-8')
                
    else: #user沒講話
        robot_reply = "沒有聽到聲音" 
    return robot_reply

def capture_image():
    with picamera.PiCamera() as camera:

        camera.start_preview()
        bot_reply('請把物品放在鏡頭前')
        bot_reply('3')
        bot_reply('2')
        bot_reply('1')
        time.sleep(1)
        rawCapture = PiRGBArray(camera)
        camera.capture(rawCapture, format="bgr")
        camera.stop_preview()
        image = rawCapture.array
        current_time = time.strftime("%Y-%m-%d %H:%M:%S ", time.localtime())
        cv2.imwrite("/home/pi/work/past_img/" + current_time + "before.jpg", image)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2YUV)
        y, u, v = cv2.split(image)
        y = cv2.equalizeHist(y)
        merged = cv2.merge([y, u, v])
        merged = cv2.cvtColor(merged, cv2.COLOR_YUV2BGR)
        cv2.imwrite("capture_image.jpg", merged)
        cv2.imwrite("/home/pi/work/past_img/" + current_time + "after.jpg", merged)

def talk_loop():
    global x
    x=0
    global nobody_count, is_recognizing, is_time_couting
    is_recognizing = False
    nobody_count=0
    while nobody_count<3:
        # print 'nobody_count', nobody_count
        print("請講話...")
        is_time_couting = True
        user_request = user_speak()
        # user_request = raw_input()
        if(user_request == 'quit'):
            break
            
        if user_request == '':
            print"沒聲音"
            continue

        if user_request.find("r")>=0 or user_request.find("這是什麼")>=0 or user_request.find("什麼功能")>=0:
            capture_image()
            is_recognizing = True
            threading.Thread(target = bot_reply, args = ("辨識中，請稍後",)).start()
            
            recognize_object = recognize_image()
            is_recognizing = False
            
            if recognize_object == 'nothing':
                bot_reply("抱歉，我不知道這是什麼")
            else :
                bot_reply("這是" + recognize_object)
                introduction_speak(recognize_object)
        else :
            robot_reply = analysis_sentence(user_request)
            bot_reply(robot_reply)
    print 'talk_loop end'
    nobody = True
    can_send_start = True


def introduction_speak(recognize_object):
    global cursor
    cursor.execute("SELECT introduction FROM commodity WHERE chinese_name = %s", (recognize_object))
    results = cursor.fetchall()
    if results[0][0] is not None:
        introduction = results[0][0].encode('utf-8')
        bot_reply(introduction)
        
def command():
    command_string='c'
    while True:
        if(command_string=='c' or command_string=='C'):
            talk_loop()
        else :
            break;
        command_string = raw_input('Press \'c\' to continue or press other key to exit :')

    
if __name__ == "__main__":
    init_loading()
    global expression, lock, nobody, is_recognizing, is_speaking
    can_send_start = False
    nobody = True
    is_recognizing = False
    is_speaking = False

    db = MySQLdb.connect("127.0.0.1", "root", "0", "ch", 3306, charset='utf8')
    cursor = db.cursor()
 
    command()
