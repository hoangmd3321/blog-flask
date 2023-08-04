import base64
from datetime import datetime, timedelta
from hashlib import md5
import json
import os
import secrets
from time import time
from flask import current_app, url_for
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import redis
import rq
from app import db, login
from app.search import add_to_index, remove_from_index, query_index


class SearchableMixin(object):
    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return cls.query.filter_by(id=0), 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        return cls.query.filter(cls.id.in_(ids)).order_by(
            db.case(when, value=cls.id)), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)



followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)



class Updateable:
    def update(self, data):
        for attr, value in data.items():
            setattr(self, attr, value)


class Token(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    access_token = db.Column(db.String(64), index=True)
    access_expiration = db.Column(db.DateTime)
    refresh_token = db.Column(db.String(64), index=True)
    refresh_expiration = db.Column(db.DateTime)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

    @property
    def access_jwt_token(self):
        return jwt.endcode({'token' : self.access_token},
                            current_app.config['SECRET_KEY'],
                            algorithm = 'HS256')

    def generate(self):
        self.access_token = secrets.token_urlsafe()
        self.access_expiration = datetime.now() + timedelta(minutes = current_app.config['ACCESS_TOKEN_EXPIRE_MINS'])
        self.refresh_token = secrets.token_urlsafe()
        self.refresh_expiration = datetime.now() + timedelta(days = current_app.config['REFRESH_TOKEN_EXPIRE_DAYS'])

    def expire(self, delay=None):
        if delay is None:
            #add 5 seconds delay for concurrent requests
            delay = 5 if not current_app.testing else 0
        self.access_expiration = datetime.utcnow() + timedelta(seconds = delay)
        self.refresh_expiration = datetime.utcnow() + timedelta(seconds = delay)
    
    @staticmethod
    def clean():
        """Remove any tokens that have been expired for more than a day."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        db.session.execute(db.delete(Token).where(Token.refresh_expiration < yesterday))

    @staticmethod
    def from_jwt(access_jwt_token):
        access_token = None
        try:
            access_token = jwt.decode(access_jwt_token, current_app.config['SECRET_KEY'],
                                    algorithm=['HS256'])['token']
            return db.session.execute(db.select(Token).filter_by(access_token=access_token)).scalar()
        except jwt.PyJWTError:
            pass

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    about_me = db.Column(db.String(140))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    tokens = db.relationship('Token', backref = 'user', lazy = 'dynamic')
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')
    messages_sent = db.relationship('Message',
                                    foreign_keys='Message.sender_id',
                                    backref='author', lazy='dynamic')
    messages_received = db.relationship('Message',
                                        foreign_keys='Message.recipient_id',
                                        backref='recipient', lazy='dynamic')
    last_message_read_time = db.Column(db.DateTime)
    notifications = db.relationship('Notification', backref='user',
                                    lazy='dynamic')
    tasks = db.relationship('Task', backref='user', lazy='dynamic')


    def __repr__(self):
        return '<User {}>'.format(self.username)

    @property
    def url(self):
        return url_for('api.get_user_id', id = self.id)

    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')

    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def avatar_url(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)

    def ping(self):
        self.last_seen = datetime.utcnow()

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    def followed_posts(self):
        # followed = db.session.execute(db.select(Post).join(
        #         followers, followers.c.followed_id == Post.user_id).filter_by(
        #         followers.c.follower_id == self.id))
        followed = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter_by(
                followers.c.follower_id == self.id)
        # own = db.session.execute(db.select(Post).filter_by(user_id=self.id))
        own = Post.query.filter_by(user_id=self.id)
        # return db.session.execute(db.union(followed, own).order_by(Post.timestamp.desc())).scalars()
        return followed.union(own).order_by(Post.timestamp.desc())

    def generate_reset_password_token(self):
        return jwt.encode(
            {'reset_email': self.email, 'exp': time() + current_app.config['RESET_TOKEN_MINS']},
            current_app.config['SECRET_KEY'], algorithm='HS256')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            email = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_email']
        except jwt.PyJWTError:
            return
        
        return db.session.execute(db.select(User).filter_by(email=email))
    
    def generate_auth_token(self):
        token = Token(user=self)
        token.generate()
        return token
    

    @staticmethod
    def verify_access_token(access_jwt_token, refresh_token=None):
        token = Token.from_jwt(access_jwt_token)
        if token:
            if token.access_expiration > datetime.utc.now():
                token.user.ping()
                db.session.commit()
                return token.user

    @staticmethod
    def verify_refresh_token(refresh_token, access_jwt_token):
        token = Token.from_jwt(access_jwt_token)
        if token and token.refresh_token == refresh_token:
            if token.refresh_expiration > datetime.utc.now():
                return token
            
            token.user.revoke_all()
            db.session.commit()


    def revoke_token(self):
        db.session.execute(db.delete(Token).where(Token.user == self))


    

    def new_messages(self):
        last_read_time = self.last_message_read_time or datetime(1900, 1, 1)
        return Message.query.filter_by(recipient=self).filter(
            Message.timestamp > last_read_time).count()

    def add_notification(self, name, data):
        self.notifications.filter_by(name=name).delete()
        n = Notification(name=name, payload_json=json.dumps(data), user=self)
        db.session.add(n)
        return n

    def launch_task(self, name, description, *args, **kwargs):
        rq_job = current_app.task_queue.enqueue('app.tasks.' + name, self.id,
                                                *args, **kwargs)
        task = Task(id=rq_job.get_id(), name=name, description=description,
                    user=self)
        db.session.add(task)
        return task

    def get_tasks_in_progress(self):
        return Task.query.filter_by(user=self, complete=False).all()

    def get_task_in_progress(self, name):
        return Task.query.filter_by(name=name, user=self,
                                    complete=False).first()

    # def to_dict(self, include_email=False):
    #     data = {
    #         'id': self.id,
    #         'username': self.username,
    #         'last_seen': self.last_seen.isoformat() + 'Z',
    #         'about_me': self.about_me,
    #         'post_count': self.posts.count(),
    #         'follower_count': self.followers.count(),
    #         'followed_count': self.followed.count(),
    #         '_links': {
    #             'self': url_for('api.get_user', id=self.id),
    #             'followers': url_for('api.get_followers', id=self.id),
    #             'followed': url_for('api.get_followed', id=self.id),
    #             'avatar': self.avatar(128)
    #         }
    #     }
    #     if include_email:
    #         data['email'] = self.email
    #     return data

    # def from_dict(self, data, new_user=False):
    #     for field in ['username', 'email', 'about_me']:
    #         if field in data:
    #             setattr(self, field, data[field])
    #     if new_user and 'password' in data:
    #         self.set_password(data['password'])

    


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Post(SearchableMixin, db.Model):
    __searchable__ = ['body']
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    language = db.Column(db.String(5))

    def __repr__(self):
        return '<Post {}>'.format(self.body)
    
    @property
    def url(self):
        return url_for('api.posts.get', id=self.id)


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

    def __repr__(self):
        return '<Message {}>'.format(self.body)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.Float, index=True, default=time)
    payload_json = db.Column(db.Text)

    def get_data(self):
        return json.loads(str(self.payload_json))


class Task(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    name = db.Column(db.String(128), index=True)
    description = db.Column(db.String(128))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    complete = db.Column(db.Boolean, default=False)

    def get_rq_job(self):
        try:
            rq_job = rq.job.Job.fetch(self.id, connection=current_app.redis)
        except (redis.exceptions.RedisError, rq.exceptions.NoSuchJobError):
            return None
        return rq_job

    def get_progress(self):
        job = self.get_rq_job()
        return job.meta.get('progress', 0) if job is not None else 100