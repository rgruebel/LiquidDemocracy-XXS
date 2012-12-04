from flask import Flask, session, render_template, request, redirect, url_for, escape, flash, g, abort, jsonify
from model import Graph
from datetime import datetime
from utils import date_diff
from collections import deque
import werkzeug
import thread
import re
import operator
import time
# configuration
DATABASE = 'graphdatabase'
DEBUG = True
SECRET_KEY = 'blubber'
USERNAME = 'tobias'
PASSWORD = 'bla'
ADMIN = 'admin'

app = Flask(__name__)
app.config.from_object(__name__)

db = Graph()

@app.template_filter('parlamentTitle')
def parlamentTitle(eid): 
  return db.parlaments.get(eid).title

@app.template_filter('getParlaments')
def getParlaments(eid): 
  v = db.vertices.get(eid)
  if v.element_type == 'instance':
    ps = [p for p in v.outV('instanceHasParlament')]
  elif v.element_type == 'proposal':
    ps = [p for p in v.outV('proposalHasParlament')]
  #TODO eid in die dicts mit einfuegen! 
  ds = []
  for p in ps: 
    d = p.data() 
    d['eid'] = p.eid
    ds.append(d)
  return ds

@app.template_filter('getPeople')
def getPeople(eid):
  ''' returns all people of the Instance eid '''
  q =  '''START i=node({i_eid}) 
          MATCH i-[:hasPeople]->p 
          RETURN ID(p), p.username
       '''
  people = db.cypher.table(q,dict(i_eid=eid))[1] # Fetch the people from neo4j ...
  peopleDict = [dict(p_eid = p[0], 
                     username = p[1])
                          for p in people]
  return peopleDict 

@app.template_filter('getProposals')
def getProposals(eid): 
  ''' returns all proposals of the Instance eid'''
  q = '''START i=node({i_eid})
         MATCH i-[:hasProposal]->pr
         RETURN ID(pr), pr.title
      '''
  proposals = db.cypher.table(q,dict(i_eid=eid))[1] # Fetch the propsals from neo4j ...
  proposalDict = [dict(p_eid = p[0],
                       title = p[1])
                          for p in proposals]
  return proposalDict

@app.template_filter('getDelegations')
def getDelegations(eid):
  q='''START i=node({userID}) MATCH i - [:personDelegation] -> hyperEdge , 
      hyperEdge-[:delegationPerson]->person,hyperEdge -[r?:delegationProposal|delegationParlament]->type  
      RETURN ID(hyperEdge),hyperEdge.datetime_created,ID(person), person.username,TYPE(r),ID(type),type.title'''
  delegations = db.cypher.table(q,dict(i_eid=eid, userID=session['userId']))[1]
  delegationsDict = [dict(delegationID=p[0],
                    delegationCreated = date_diff(datetime.utcfromtimestamp(p[1]), datetime.today()), 
                    username   = p[3], 
                    p_eid   = p[2],
                    delegationtype=p[4],
                    typeID=p[5],
                    title=p[6]
                    )
                          for p in delegations]              
  return delegationsDict 

@app.template_filter('person2proposals')
def person2proposals(p_eid):
  ''' all proposals of a given person p_eid in a given instance g.i_eid in descending 
      order, i.e. props[1] contains the newest proposal, props[-1] contains the oldest proposal.
  '''
  q = '''START p=node({peid}), inst=node({ieid})
         MATCH p-[i:issued]->pr<-[:hasProposal]-inst
         WHERE pr.element_type="proposal"
         RETURN ID(pr), pr.title, pr.datetime_created ORDER BY pr.datetime_created DESC
      '''
  props = db.cypher.table(q,dict(peid=p_eid, ieid=g.i_eid))[1] # Fetch the proposals from neo4j ...
  propsDict = [dict(created = date_diff(datetime.utcfromtimestamp(p[2]), datetime.today()), 
                    title   = p[1], 
                    p_eid   = p[0])
                          for p in props]                      # ... and create a dict-object ...
  return propsDict                                             # ... and return it.

@app.template_filter('person2comments')
def person2comments(p_eid):
  ''' all comments of a given person p_eid in a given instance g.i_eid in descending 
      order, i.e. comments[1] contains the newest comment, comments[-1] contains the oldest comment.
  '''
  q = '''START p=node({peid}), inst=node({ieid})
         MATCH p-[i:issuesComment]->co<-[:hasComment]-pr<-[:hasProposal]-inst
         WHERE co.element_type="comment"
         RETURN ID(co), co.title, co.datetime_created, ID(pr) ORDER BY co.datetime_created DESC
      '''
  comments = db.cypher.table(q,dict(peid=p_eid, ieid=g.i_eid))[1] # Fetch the comments from neo4j ...
  commentsDict = [dict(created = date_diff(datetime.utcfromtimestamp(c[2]), datetime.today()), 
                       title   = c[1], 
                       c_eid   = c[0],
                       p_eid   = c[3])
                          for c in comments]                      # ... and create a dict-object ...
  return commentsDict                                             # ... and return it.
 

@app.template_filter('person2votesProposals')
def person2votesProposals(p_eid):
  ''' all proposals votings of a given person p_eid in a given instance g.i_eid in temporal descending 
      order, i.e. propVotes[0] contains the latest vote, propVotes[-1] contains the oldest vote.
  '''
  q = '''START p=node({peid}), inst=node({ieid})
         MATCH p-[v:votes]->pr<-[:hasProposal]-inst
         WHERE pr.element_type="proposal"
         RETURN v.created, v.pro, pr.title, ID(pr) ORDER BY v.created DESC '''
  propVotes     = db.cypher.table(q,dict(peid=p_eid, ieid=g.i_eid))[1] # Fetch the votes from neo4j ...
  propVotesDict = [dict(created = date_diff(datetime.utcfromtimestamp(p[0]), datetime.today()), 
                        pro     = p[1], 
                        title   = p[2], 
                        p_eid   = p[3]) 
                             for p in propVotes]                       # ... and create a dict-object ...
  return propVotesDict                                                 # ... and return it.


@app.template_filter('person2votesComments')
def person2votesComments(p_eid):
  ''' all comments votings of a given person p_eid in a given instance g.i_eid in temporal descending 
      order, i.e. coVotes[0] contains the latest vote, copVotes[-1] contains the oldest vote.
  '''
  q = '''START p=node({peid}), inst=node({ieid})
         MATCH p-[v:votes]->co<-[:hasComment]-pr<-[:hasProposal]-inst
         WHERE co.element_type="comment"
         RETURN v.created, v.pro, co.title, ID(co), ID(pr) ORDER BY v.created DESC '''
  coVotes     = db.cypher.table(q,dict(peid=p_eid, ieid=g.i_eid))[1] # Fetch the votes from neo4j ...
  coVotesDict = [dict(created = date_diff(datetime.utcfromtimestamp(c[0]), datetime.today()), 
                        pro     = c[1], 
                        title   = c[2], 
                        c_eid   = c[3],
                        p_eid   = c[4])
                             for c in coVotes]                       # ... and create a dict-object ...
  return coVotesDict                                                 # ... and return it.

@app.template_filter('iconize')
def compact(s): 
  ''' return the first few words of the text s in order to produce 
      a short description of an entry's or comment's text '''
  if len(s)<=200:  return s
  s=s[:200]
  s2 = filter(lambda c: c!='\n', s)
  m = re.match(r".*\s", s2) 
  return s2 if not m else s2[:m.end()] + ' ... '

@app.template_filter('i_eid2title')
def eid2title(i_eid):
  instance = db.instances.get(i_eid)
  return instance.title

@app.url_defaults
def add_i_eid(endpoint, values):
  if 'i_eid' in values or not g.i_eid:
    return
  if app.url_map.is_endpoint_expecting(endpoint, 'i_eid'):
    values['i_eid'] = g.i_eid

@app.url_value_preprocessor
def pull_i_eid(endpoint, values):
  if values: 
    g.i_eid = values.pop('i_eid', None)
  else:
    g.i_eid = None

def data(p): 
   d = p.data()
   d['eid'] = p.eid
   return d

def issuer(eid): 
  ''' Returns the User(s) which issued the Proposal with eid "eId" '''
  if db.vertices.get(eid).element_type=='proposal': 
    return [e.outV() for e in db.vertices.get(eid).inE('issued') ]
  elif db.vertices.get(eid).element_type=='comment':
    return [e.outV() for e in db.vertices.get(eid).inE('issuesComment')]

def countVotes(propId):
  ''' Calculates the votes count '''
  return countVotesUp(propId) - countVotesDown(propId)

def countVotesDown(eid):
  ''' Calculates the votes "down" '''
  v = db.vertices.get(eid)
  return sum([ -1 for voteRel in v.inE('votes') if voteRel.pro==0])

def countVotesUp(eid):
  ''' Calculates the votes "up" '''
  v = db.vertices.get(eid)
  return sum([1 for voteRel in v.inE('votes') if voteRel.pro==1])

def proposalsByVotes(i_eid):
  ''' Sorts proposals of a specific instance by vote-count '''
  instance = db.instances.get(i_eid)
  proposals = instance.outV('hasProposal')
  return sorted(proposals, key=lambda p:len(list(p.inE('votes'))), reverse=True)

def commentsByVotes(prop_id):
  ''' Sorts proposals by vote-count '''
  comments = db.comments.get(prop_id).outV('hasComment') 
  return sorted(comments, key=lambda c:len(list(c.inE('votesComment'))), reverse=True)

def v2Dict(eid, loggedUserEid=None):
  ''' v = proposal OR comment 
      The resulting dict-Object d collects 
        - the person which issued the proposal/comment, 
        - the vote-counts
        - the creation date ''' 
  v = db.vertices.get(eid)
  d = dict(title = v.title, body=v.body, eid=eid, ups=v.ups, downs=v.downs)
  users = issuer(eid)
  d['username'] = users[0].username if users else None
  d['userid'] = users[0].eid if users else None
  d['voteCountUp'] = countVotesUp(eid)
  d['voteCountDown'] = countVotesDown(eid)
  d['created'] = date_diff(v.datetime_created, datetime.today())
  if loggedUserEid: 
    loggedUser = db.people.get(loggedUserEid)
    votes = [voteEdge for voteEdge in loggedUser.outE('votes') if voteEdge.inV() == v]
    if votes:
      d['upvoted']   = (votes[0].pro == 1)
      d['downvoted'] = (votes[0].pro == 0)
  return d

def i2Dict(i_eid, loggedUserEid=None): 
  ''' i_eid = instance 
      Collects information about an instance: 
        title, body, created, numberUsers, numberVotes, numberProposals, numberComments'''
  instance = db.instances.get(i_eid)
  d = dict(title=instance.title, body=instance.body, eid=i_eid)
  d['created']     = date_diff(instance.datetime_created, datetime.today())
  d['numberUsers'] = len(list(instance.outV('hasPeople')))
  proposals = list(instance.outV('hasProposal'))
  d['numberProposals'] = len(proposals)
  d['numberVotes'] = sum([len(list(p.inE('votes'))) for p in proposals])
  d['numberComments'] = sum([len(list(p.outE('hasComment'))) for p in proposals])
  # Alternatively, the following Cypher-Query could be used: 
  # q = '''START i=node({i_eid}) 
  #   MATCH i-[:hasProposal]->p-[:hasComment]->c
  #   RETURN count(c)'''
  # d['numberComments'] = db.cypher.table(q,dict(i_eid=i_eid))[1][0][0] 
  return d

def person2Dict(person): 
  p = person.data()
  p['eid'] = person.eid
  return p

#delegationProposal -> priorltaet 1
#delegationParlament -> prioritaet 2
#nur delegationPerson -> prioritaet 3
def countVotingWeight(personID,proposalID):
  '''Zaehlt das Stimmgewicht der uebergebenen Person bei dem uerbegebenen Vorschlag.
    Die child_list enthaelt am schluss alle ids der gezaehlten Stimmen.
  '''
  db=Graph()
  #Liste welche die eid jeder gueltigen Person(Stimme) enthaelt
  child_list=[personID]
  #Alle eids welche beim uebergebenen proposalID bereits selbst gevotet haben(pfad der delegation endet dann)
  votes=[p.eid for p in db.proposals.get(proposalID).inV('votes')]
  #Stack der zu zu durchlaufenden nodes, wird erweitert in der Schleife
  to_crawl=deque(list(db.vertices.get(personID).inV("delegationPerson")))
  while to_crawl:
    node = to_crawl.popleft()
    if node.element_type=='delegation':
      delegationDetail = list(node.outV())
      #Wenn delegation zu einem Proposal zeigt und dieses auch noch passende Id hat.
      #In meiner ueberlegung die hoechste Prioritaet.
      if any(x.element_type=='proposal' and x.eid ==proposalID for x in delegationDetail):
        to_crawl.extend(list(node.inV('personDelegation')))
      #Hat ein andere User eine delegation bekommen welche direkt zum Proposal geht?
      elif not any(i.eid==proposalID for d in node.inV('personDelegation').next().outV('personDelegation') for i in d.outV('delegationProposal')):
        #Handelt es sich um eine Delegation fuer ein Parlament?
        if any(x.element_type=='parlament' for x in delegationDetail):
          #Hat das Proposal mehrere Delegationen vom Benutzer?Dann gilt die zuletzt angelegte.
          parlaments=[(p.eid,p.datetime_created) for p in db.proposals.get(proposalID).outV('proposalHasParlament')]
          parlaments.sort(key=lambda r: r[1],reverse=True)
          if not parlaments==[] and node.outV('delegationParlament').next().eid == parlaments[0][0]:
            to_crawl.extend(list(node.inV('personDelegation')))     
        elif not any(x.element_type=='proposal' for x in delegationDetail):
          to_crawl.extend(list(node.inV('personDelegation')))
    elif node.element_type=='person':
      #Wenn Person selbst gevotet hat Pfad unterbrechen, ansonsten stimme zaehlen und weiter maschieren
      if not node.eid in votes:
        if not node.eid in child_list:
          child_list.append(node.eid)
          to_crawl.extend(list(node.inV('delegationPerson')))
      else:
        pass #User hat bereits gevotet
  return child_list
def affectedVotes():
  '''ueberprueft bei welchen Proposals das Voting neu berechent werden muss beim anlegen oder loeschen einer delegation.
  Beim erstellen:delegation erst erstellen dann Voting neu berechnen'''
  q=  '''START i=node({userid}) 
    MATCH i-[:personDelegation*]->x-[:delegationPerson|personDelegation|votes*] ->p 
    WHERE (p.element_type="proposal") RETURN distinct ID(p)
    '''
  return reduce(operator.add, db.cypher.table(q,dict(userid=session['userId']))[1])

def recalculateAffectedVotes(result):
  '''Berechnet die uebergebenden Proposals neu'''
  db=Graph()
  for p in result:
    q='''START i=node({proposalid}) MATCH p-[r:votes]->i RETURN ID(p) AS voterID,r.pro AS pro'''
    votes=db.cypher.table(q,dict(proposalid=p))[1]
    downs=0
    ups=0
    for v in votes:
      if v[1]==1:
        ups+=len(countVotingWeight(v[0],p))
      elif v[1]==0:
        downs+=len(countVotingWeight(v[0],p))
    c_p=db.vertices.get(p)
    c_p.ups=ups
    c_p.downs=downs
    c_p.save() 
  return result
#-------------------- The view functions ----------------------------------------
#   * Instances
#     - show_instances, add_instance
#   * Proposals 
#     - show_proposal , show_single_proposal, add_proposal, delete_proposal
#   * Comments
#     - add_comment
#   * Votes
#     - vote
#   * People
#     - login, logout, signin, login_instance
#     - show_person, show_people
# -------------------------------------------------------------------------------

@app.route('/')
def show_instances():
  user = db.people.get(session['userId']) if session.get('logged_in') else None
  if user and not session['isAdmin']: 
     instances = [i2Dict(i.eid, user) for i in db.instances.get_all() if user in i.outV('hasPeople')]
  else: 
     instances = [i2Dict(i.eid) for i in db.instances.get_all()]
  return render_template('show_instances.html', instances=instances)

@app.route('/addinstance', methods=['POST'])
def add_instance(): 
  if not (session.get('logged_in') and session['isAdmin']): 
    abort(401)  
  instance = db.instances.create(title=request.form['title'], body=request.form['body'])
  flash('Neue Instanz haette angelegt werden muessen') 
  return redirect(url_for('show_instances'))

@app.route('/<int:i_eid>/proposals')
def show_proposals(): 
  proposals = []
  userEid = db.people.get(session['userId']).eid if session.get('logged_in') else None
  instance = db.instances.get(g.i_eid)
  # i = dict(title=instance.title, eid=g.i_eid)
  for proposal in proposalsByVotes(g.i_eid):
    p = v2Dict(proposal.eid, loggedUserEid=userEid)
    proposals.append(p)
  return render_template('show_proposals.html', entries=proposals)

@app.route('/<int:i_eid>/proposal/<int:prop_id>')
def show_single_proposal(prop_id):
   userEid = db.people.get(session['userId']).eid if session.get('logged_in') else None
   proposal = v2Dict(prop_id, loggedUserEid=userEid)
   comments = []
   for comment in commentsByVotes(prop_id):
     c = v2Dict(comment.eid, loggedUserEid=userEid)
     comments.append(c)
   return render_template('show_single_proposal.html', proposal=proposal, comments=comments)

@app.route('/<int:i_eid>/addproposal',methods=['POST'])
def add_proposal():
  if not session.get('logged_in'):
    abort(401)
  prop = db.proposals.create(title=request.form['title'], body=request.form['body'], ups=0, downs=0)
  if 'parlament' in request.form: 
    p = list(db.parlaments.index.lookup(title=request.form['parlament']))
    if p: 
      db.proposalHasParlament.create(prop,p[0])
  instance = db.instances.get(g.i_eid)
  user = db.people.get(session['userId'])
  db.issued.create(user,prop)           # Edge1: User issues Proposal
  db.hasProposal.create(instance, prop) # Edge2: Proposal belongs to current Instance
  flash('Neuer Eintrag erfolgreich erstellt')
  return redirect(url_for('show_proposals'))

@app.route('/<int:i_eid>/deleteproposal/<int:prop_id>')
def delete_proposal(prop_id):
  if not session.get('logged_in'):
    abort(401)
  proposal = db.proposals.get(prop_id)
  for e in proposal.inE('hasProposal'): 
    db.hasProposal.delete(e.eid) 
  resp = db.proposals.delete(prop_id)
  flash('Eintrag geloescht')
  return redirect(url_for('show_proposals'))

@app.route('/<int:i_eid>/addcomment/<int:prop_id>',methods=['POST'])
def add_comment(prop_id):
  if not session.get('logged_in'):
    abort(401)
  comment = db.comments.create(title=request.form['title'], body=request.form['body']) 
  user = db.people.get(session['userId'])
  db.issuesComment.create(user,comment) 
  db.hasComment.create(db.proposals.get(prop_id), comment)
  flash('Neuer Kommentar erfolgreich erstellt')
  return redirect(url_for('show_single_proposal', prop_id=prop_id))

@app.route('/_vote')
def vote():
  ''' Voting a proposoal or comment with Id eid. Upvote means pro==1, Downvote means pro==0'''
  pro=request.args.get('pro',0,type=int)
  eid=request.args.get('eid',0,type=int)
  voted=0
  if not session.get('logged_in'):
    abort(401)
  loggedUser = db.people.get(session['userId'])
  c_p = db.vertices.get(eid)             # c_p is a comment or a proposal
  voteRels = [rel for rel in loggedUser.outE('votes') if rel.inV() == c_p]
  if voteRels and voteRels[0].pro!=pro:  # i.e.: user undoes vote => delete Edge
    db.votes.delete(voteRels[0].eid)
    #flash('Stimme rueckgaengig gemacht')
  if voteRels and voteRels[0].pro==pro:  # i.e.: Voting up/down a second time is not allowed.
    abort(401)
  if not voteRels:                       # i.e.: No "votes"-edge exists => create new "votes"-Edge
    db.votes.create(loggedUser,c_p, pro=pro)
    voted=1
    if pro: 
      #flash('Erfolgreich dafuer gestimmt')
      pass 
    else:   
      #flash('Erfolgreich dagegen gestimmt')
      pass
  recalculateAffectedVotes([eid])
  c_p = db.vertices.get(eid)  
  if c_p.element_type == 'comment':
    proposal = c_p.inV('hasComment').next()
    #return redirect(url_for('show_single_proposal', prop_id=proposal.eid))
  #return redirect(url_for('show_proposals'))

  list = [
              {'ups': c_p.ups, 'downs': c_p.downs,'voted':voted},
             ]
  return jsonify(results = list)

@app.route('/<int:i_eid>/login',methods=['POST','GET'])
def login_instance(): 
  error = None
  if request.method == 'POST':
    username = request.form['username'] ; password = request.form['password']
    instance = db.instances.get(g.i_eid)
    users = [u for u in db.people.index.lookup(username=username) if u in instance.outV('hasPeople')]
    if users and users[0].password==password: 
      session['logged_in'] = True
      session['userId'] = users[0].eid ; session['username'] = users[0].username 
      session['isAdmin'] = users[0].username==app.config['USERNAME']
      s = "Du hast Dich in Instanz %s eingeloggt" % instance.title
      flash(s) 
      return redirect(url_for('show_proposals'))
    elif not users:
      error = 'Ungueltiger Benutzername'
    else:
      error = 'Ungueltiges Passwort'
  return render_template('login.html', instances=None, error=error)

@app.route('/login', methods=['POST','GET'])
def login(): 
    error = None 
    if request.method == 'POST':
      username = request.form['username'] ; password = request.form['password'] ; instancetitle = request.form['instancetitle']
      instance = db.instances.index.lookup(title=instancetitle).next()
      users = [u for u in db.people.index.lookup(username=username) if u in instance.outV('hasPeople')] 
      if users and users[0].password==password: 
        session['logged_in'] = True
        session['userId'] = users[0].eid ; session['username'] = users[0].username
        session['isAdmin'] = users[0].username==app.config['USERNAME']
        s = "Du hast Dich in Instanz %s eingeloggt" % instancetitle
        flash(s) 
        return redirect(url_for('show_proposals', i_eid=instance.eid))
      elif not users:
        error = 'Ungueltiger Benutzername fuer Instanz %s' % instancetitle
      else:
        error = 'Ungueltiges Passwort'
    return render_template('login.html', i_eid=None, instances = [dict(title=i.title) for i in db.instances.get_all()], error=error)
  
@app.route('/<int:i_eid>/logout')
def logout():
  ''' Deletes the cookies and redirects to show_instances'''
  session.pop('logged_in', None)
  session.pop('userId',None)
  session.pop('username',None)
  session.pop('isAdmin',None)
  flash('Du hast Dich ausgeloggt')
  return redirect(url_for('show_instances'))

@app.route('/<int:i_eid>/signin', methods=['POST', 'GET'])
def signin():  
  ''' There are two cases: 
      1. A new user is created in the current instance
      2. An existing user is associated with the current instance '''
  error = None
  if request.method == 'POST':
    if 'username' in request.form:  
      username = request.form['username'] ; pass1 = request.form['password1'] ; pass2 = request.form['password2']
      email = request.form['email'] ; vorname = request.form['vorname'] ; nachname = request.form['nachname']
      users = [p for p in db.people.index.lookup(username=username)] 
      if users: #Benutzername schon vorhanden?
        error = 'Benutzername existiert schon'
      elif pass1!=pass2: 
        error = 'Passwort nochmals eingeben!'
      elif not (email and vorname and nachname and username): 
        error = 'Eingabedaten unvollstaendig!'
      else: 
        instance = db.instances.get(g.i_eid)
        user = db.people.create(firstname=vorname, secondname=nachname, username=username, password=pass1, email=email)
        db.hasPeople.create(instance, user)
        flash('Benutzer erfolgreich angelegt')
        return redirect(url_for('login_instance'))
    if 'username1' in request.form: 
      username = request.form['username1'] 
      passw = request.form['password']
      # does username alread exist?
      users = list(db.people.index.lookup(username=username))  
      if not users: 
        flash('Der angegebene Benutzername existiert aber noch nicht')
        return redirect(url_for('signin'))
      else: 
        user = users[0]
        if user.password != passw: 
            flash('Password war falsch')
            return redirect(url_for('signin'))
        else: 
            instance = db.instances.get(g.i_eid)
            db.hasPeople.create(instance, user)
            flash('Benutzer erfolgreich zur Instanz hinzugefgt')
            return redirect(url_for('login_instance'))
  return render_template('signin.html', error=error)

@app.route('/<int:i_eid>/logoutLogin/<int:p_eid>')
def logoutLogin(p_eid):
  ''' Wird ein User geklickt, so wird automatisch versucht, den aktuellen Benutzer auszuloggen und 
      mit dem neuen Benutzer einzuloggen '''
  if session.get('logged_in'): 
    flash('Du hast Dich ausgeloggt') 
    session.pop('logged_in', None)
    session.pop('userId',None)
    session.pop('username',None)
    session.pop('isAdmin',None)
  session['userId']=p_eid
  session['username']=db.people.get(p_eid).username
  return redirect(url_for('login_instance'))

@app.route('/<int:i_eid>/person/<int:p_eid>')
def show_person(p_eid):
  if not session.get('logged_in'):
        abort(401)
  person = db.people.get(p_eid)
  return render_template('show_person.html', person=dict(p_eid=p_eid, firstname=person.firstname,\
                                                         secondname=person.secondname,\
                                                         username=person.username, email=person.email))

@app.route('/<int:i_eid>/persons')
def show_people():
  instance = db.instances.get(g.i_eid)
  people = [person2Dict(p) for p in instance.outV('hasPeople')] 
  return render_template('show_people.html', people = people, 
                                             instance = dict(title=instance.title,\
                                                             eid=instance.eid))

@app.route('/<int:i_eid>/parlaments')
def show_parlaments(): 
  q_pa = '''START i=node({i_eid})
            MATCH i-[:instanceHasParlament]->pa
            RETURN pa'''
  pa = db.cypher.query(q_pa, dict(i_eid=g.i_eid))
  parlaments = [data(p) for p in pa]
  q_numProp = '''START pa=node({pa_eid})
                 MATCH pa<-[:proposalHasParlament]-pr
                 RETURN COUNT(pr)'''
  for p in parlaments: 
    erg = db.cypher.table(q_numProp, dict(pa_eid=p['eid']))[1]
    p['numberProposals'] = 0 if not erg else erg[0][0]
  return render_template('show_parlaments.html', parlaments=parlaments)

@app.route('/<int:i_eid>/addparlament', methods=['POST'])
def add_parlament(): 
  if not (session.get('logged_in') and session['isAdmin']): 
    abort(401)
  q = '''START i=node({i_eid}) 
         MATCH i-[:instanceHasParlament]->pa
         WHERE pa.title = {title}
         RETURN pa'''
  pa = list(db.cypher.query(q, dict(i_eid=g.i_eid, title=request.form['title'])))
  if pa: 
    flash('Parlament wurde nicht angelegt! Es existiert schon in dieser Instanz')
  else:  
    instance = db.instances.get(g.i_eid)
    parlament = db.parlaments.create(title=request.form['title'], body=request.form['body'])
    db.instanceHasParlament.create(instance, parlament) 
    flash('Neues Parlament wurde angelegt') 
  return redirect(url_for('show_parlaments'))


@app.route('/<int:i_eid>/delegate_overview')
def delegateOverview():   
  return render_template('delegate.html', overview=True)

@app.route('/<int:i_eid>/delegate_parlament/<int:parl_eid>')
def delegateParlament(parl_eid): 
  parlament = db.parlaments.get(parl_eid)
  return render_template('delegate.html', parlament=parl_eid)

@app.route('/<int:i_eid>/delegate_proposal/<int:pr_eid>')
def delegateProposal(pr_eid): 
  return render_template('delegate.html', proposal=pr_eid)

@app.route('/<int:i_eid>/delegate_person/<int:p_eid>')
def delegatePerson(p_eid): 
  return render_template('delegate.html', person=p_eid)

@app.route('/<int:i_eid>/delegate',methods=['POST'])
def delegate(): 
  postData=werkzeug.urls.url_decode(request.form['param'],'utf-8')
  overwrite=int(request.form['overwrite'])

  q='''START i=node({userid}) 
      MATCH i-[:personDelegation]->d-[?:delegationParlament|delegationProposal]->p,d-[:delegationPerson]->u 
      RETURN ID(p),p.element_type,ID(d),ID(u)'''
  delete=None
  result=db.cypher.table(q,dict(userid=session['userId']))[1]
  if overwrite == 0:
    if postData['span'] == 'proposal':
      if any(p[0]==int(postData['proposal']) and p[1] == 'proposal' for p in result):
        return jsonify(results=[{'exists': 1}])
    elif postData['span']== 'parlament':
      if any(p[0]==int(postData['parlament']) and p[1] == 'parlament' for p in result):
        return jsonify(results=[{'exists': 1}])
    else:
      if any(p[1] == None for p in result):
        return jsonify(results=[{'exists': 1}])
  else:
    if postData['span'] == 'proposal' or postData['span'] == 'parlament':     
      delete=[p for p in result if p[0]==int(postData[postData['span']])][0][2]
      print delete
    else:
      delete=[p for p in result if p[1]==None][0][2]
      print delete
  
  person = int(postData['person']) if 'person' in postData else None
  proposal = int(postData['proposal']) if 'proposal' in postData else None
  parlament = int(postData['parlament']) if 'parlament' in postData else None
  span = postData['span'] # span is one of 'parlament' / 'proposal' / 'all'
 
  # Create edges: 
  delegation = db.delegations.create()
  personDelegationEdge = db.personDelegation.create(db.people.get(session['userId']), delegation)
  delegationPersonEdge = db.delegationPerson.create(delegation, db.people.get(person))
  if span=='parlament': # make edge from delegation object to parlament
    delegationParlamentEdge = db.delegationParlament.create(delegation, db.parlaments.get(parlament))
  elif span=='proposal': # make edge from delegaton object to proposal
    delegationProposalEdge = db.delegationProposal.create(delegation, db.proposals.get(proposal))
  # else:   # here span=='all' should hold
  #    pass # no additonal edges!

  affected=affectedVotes()
  #Delete old delegation
  if not delete is None:
    for e in db.delegations.get(delete).bothE():
      db.client.delete_edge(e._id)
    db.client.delete_vertex(delete)
  def bgrWorker(req,aff):
      with app.test_request_context():
        from flask import request
        request = req
        recalculateAffectedVotes(aff)

  thread.start_new_thread(bgrWorker, (request,affected))
  
  list = [
              {'exists': 0}
            ]
  return jsonify(results = list)


@app.route('/<int:i_eid>/deleteDelegation/<int:eid>')
def deleteDelegation(eid):
  affected=affectedVotes()
  for e in db.delegations.get(eid).bothE():
    db.client.delete_edge(e._id)
  db.client.delete_vertex(eid)
  flash('Delegation geloescht')
  #recalculateAffectedVotes(affected)
  def bgrWorker(req,aff):
      with app.test_request_context():
        from flask import request
        request = req
        recalculateAffectedVotes(aff)

  thread.start_new_thread(bgrWorker, (request,affected))
  return redirect(url_for('delegateOverview'))


@app.route('/_add_numbers')
def add_numbers():
  a = request.args.get('a',0,type=int)
  b = request.args.get('b',0,type=int)
  #return jsonify(result=a+b)
  list = [
              {'a': 1, 'b': 2},
              {'a': 5, 'b': 10}
             ]
  return jsonify(results = list)

def initdb():
  users = [p for p in db.people.index.lookup(username=app.config['USERNAME'])]
  if not users: 
    db.people.create(username=app.config['USERNAME'], \
                     firstname=app.config['USERNAME'], \
                     secondname=app.config['USERNAME'], \
                     password=app.config['PASSWORD'], \
                     email='email')

initdb()
if __name__ == '__main__':
  app.run(host='0.0.0.0')
