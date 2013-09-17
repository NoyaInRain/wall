# Wall

# Python forward compatibility
from __future__ import (division, absolute_import, print_function,
    unicode_literals)

import random
import math
from math import sin, cos
from tornado.ioloop import PeriodicCallback
from wall import Brick, Message, randstr, error_json

# TODO: port to new brick architecture

class PyngBrick(Brick):
    id = 'pyng'
    maintainer = 'Sven James <sven.jms AT gmail.com>'
    js_module = 'wall.bricks.pyng'
    post_type = 'PyngPost'
    
    def __init__(self, app):
        super(PyngBrick, self).__init__(app)
        self.post = None
        
        self.tps = int(self.config.get('pyng.tps', '30'))
        self.win_score = int(self.config.get('pyng.win_score', '10'))
        
        self.mode = 'lobby'
        self.subscribers = []
        self.players = []
        self.ball = None
        self.goals = [Goal(5.0, 40.0), Goal(95.0, 60.0)]
        
        self._ticks = 0
        # TODO: stop clock / game when post is removed from the wall
        self._clock = PeriodicCallback(self._tick, int(1000 / self.tps))
        
        self.app.add_event_listener('disconnected', self._disconnected)
        self.app.add_message_handler('pyng.subscribe', self._subscribe_msg)
        self.app.add_message_handler('pyng.join', self._join_msg)
        self.app.add_message_handler('pyng.update', self._update_msg)
    
    def post_new(self, type, **args):
        if not self.post:
            self.post = PyngPost(randstr())
        return self.post
    
    def subscribe(self, user):
        self.subscribers.append(Subscriber(randstr(), user))
        return self.players
    
    def unsubscribe(self, user):
        try:
            subscriber = filter(lambda s: s.user == user, self.subscribers)[0]
        except IndexError:
            raise ValueError('user')
        self.subscribers.remove(subscriber)
    
    def join(self, user):
        if self.mode != 'lobby':
            raise ValueError('mode')
        
        player = Player(randstr(), user)
        self.players.append(player)
        
        goal = filter(lambda g: g.player is None, self.goals)[0]
        goal.player = player
        player.x = goal.x
        player.y = goal.y
        
        self._send_to_subscribers(Message('pyng.joined', player.json()))
        
        if len(self.players) == 2:
            self._start()
    
    def update(self, user, pos):
        try:
            player = filter(lambda p: p.user == user, self.players)[0]
        except IndexError:
            raise ValueError('user')
        player.y = pos * 100
        player._ups_counter += 1
    
    def _start(self):
        self.logger.info('match started')
        self.mode = 'match'
        self.ball = Ball(randstr(), 0, 0)
        self._start_round()
        self._clock.start()
    
    def _stop(self):
        self.logger.info('match stopped')
        self._clock.stop()
        self.mode = 'lobby'
        self.players = []
        self.ball = None
        for goal in self.goals:
            goal.player = None
    
    def _start_round(self):
        self.ball.x = random.uniform(45, 55)
        self.ball.y = random.uniform(45, 55)
        a = random.uniform(math.pi / 8, math.pi / 4)
        v = 50
        self.ball.dx = cos(a) * v * random.choice([-1, 1])
        self.ball.dy = sin(a) * v * random.choice([-1, 1])
    
    def _tick(self):
        if self.ball.y <= 0 or self.ball.y >= 100:
            self.ball.dy *= -1
        
        for player in self.players:
            if collides(self.ball, player):
                self.ball.dx *= -1
        
        player = None
        if self.ball.x <= 0:
            player = self.goals[1].player
        if self.ball.x >= 100:
            player = self.goals[0].player
        if player:
            player.score += 1
            if player.score == self.win_score:
                msg = Message('pyng.game_over', {'winner': player.id})
                self._send_to_subscribers(msg)
                self._stop()
            else:
                msg = Message('pyng.scored',
                    {'player': player.id, 'score': player.score})
                self._send_to_subscribers(msg)
                self._start_round()
            return
        
        self.ball.x += self.ball.dx / self.tps
        self.ball.y += self.ball.dy / self.tps
        
        snapshot = {
            'ball': self.ball.snapshot(),
            'players': [p.snapshot() for p in self.players]
        }
        self._send_to_subscribers(Message('pyng.update', snapshot))
        
        if self._ticks % self.tps == 0:
            for player in self.players:
                player.ups = player._ups_counter
                player._ups_counter = 0
                self.logger.debug(
                    'player {0}: {1} UPS'.format(player.id, player.ups))
        self._ticks += 1
    
    def _send_to_subscribers(self, msg):
        for subscriber in self.subscribers:
            subscriber.user.send(msg)
    
    def _disconnected(self, user):
        try:
            self.unsubscribe(user)
        except ValueError:
            pass
    
    def _subscribe_msg(self, msg):
        players = self.subscribe(msg.frm)
        msg.frm.send(Message(msg.type, [p.json() for p in players]))
    
    def _join_msg(self, msg):
        try:
            self.join(msg.frm)
            result = Message(msg.type)
        except ValueError as e:
            result = Message(msg.type, error_json(e))
        msg.frm.send(result)
    
    def _update_msg(self, msg):
        try:
            self.update(msg.frm, msg.data)
        except ValueError:
            pass

class PyngPost(object):
    def __init__(self, id):
        self.id = id
        self.__type__ = type(self).__name__

class Subscriber(object):
    def __init__(self, id, user):
        self.id = id
        self.user = user

class Player(object):
    def __init__(self, id, user):
        self.id = id
        self.user = user
        self.x = 0.0
        self.y = 0.0
        self.width = 1.5
        self.height = 12.0
        self.score = 0
        self.ups = 0
        self.type = type(self).__name__
        self._ups_counter = 0
    
    def json(self):
        return dict((k, v)
            for k, v in vars(self).items()
            if k != 'user' and not k.startswith('_'))
    
    def snapshot(self):
        return {'id': self.id, 'x': self.x, 'y': self.y}

class Ball(object):
    def __init__(self, id, x, y):
        self.id = id
        self.x = x
        self.y = y
        self.width = 2.0
        self.height = 2.0
        self.dx = 0.0
        self.dy = 0.0
    
    def snapshot(self):
        return {'id': self.id, 'x': self.x, 'y': self.y}

class Goal(object):
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.player = None

def collides(p, box):
    w2 = box.width / 2
    h2 = box.height / 2
    return (p.y < box.y + h2 and p.y > box.y - h2 and p.x < box.x + w2 
        and p.x > box.x - w2)

Brick = PyngBrick