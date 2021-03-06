# Standard imports
import json
from random import randrange
from bottle import route, post, get, run, template, static_file, request, app, HTTPError, abort, BaseRequest, JSONPlugin, response
import bottle as bt
# To support dynamic loading of client-specific libraries
import sys
import os
import logging.config

from datetime import datetime
import time
import arrow
from uuid import UUID
# So that we can set the socket timeout
import socket
# For decoding JWTs using the google decode URL
import urllib
import requests
# For decoding JWTs on the client side
import oauth2client.client
from oauth2client.crypt import AppIdentityError
import traceback
import xmltodict
import urllib2
import bson.json_util

# Our imports
import modeshare, zipcode, distance, tripManager, \
                 Berkeley, visualize, stats, usercache, timeline, \
                 metrics, pipeline
import emission.net.ext_service.moves.register as auth
import emission.net.ext_service.habitica.proxy as habitproxy
import emission.analysis.result.carbon as carbon
import emission.analysis.classification.inference.commute as commute
import emission.analysis.modelling.work_time as work_time
import emission.analysis.result.userclient as userclient
import emission.core.common as common
from emission.core.wrapper.client import Client
from emission.core.wrapper.user import User
from emission.core.get_database import get_uuid_db, get_mode_db
import emission.core.wrapper.motionactivity as ecwm
import emission.storage.timeseries.timequery as estt
import emission.storage.timeseries.tcquery as esttc
import emission.storage.timeseries.aggregate_timeseries as estag
import emission.storage.timeseries.cache_series as esdc
import emission.core.timer as ect
import emission.core.get_database as edb

from emission.net.api.validateToken import OpenIDTokenValidator

config_file = open('conf/net/api/webserver.conf')
config_data = json.load(config_file)
static_path = config_data["paths"]["static_path"]
python_path = config_data["paths"]["python_path"]
server_host = config_data["server"]["host"]
server_port = config_data["server"]["port"]
socket_timeout = config_data["server"]["timeout"]
log_base_dir = config_data["paths"]["log_base_dir"]

key_file = open('conf/net/keys.json')
key_data = json.load(key_file)
discoveryURI = key_data["discoveryURI"]
clientID = key_data["clientID"]

BaseRequest.MEMFILE_MAX = 1024 * 1024 * 1024 # Allow the request size to be 1G
# to accomodate large section sizes

skipAuth = False
tokenValidator = OpenIDTokenValidator(discoveryURI, clientID)
print "Finished configuring logging for %s" % logging.getLogger()
app = app()

# On MacOS, the current working directory is always in the python path However,
# on ubuntu, it looks like the script directory (api in our case) is in the
# python path, but the pwd is not. This means that "main" is not seen even if
# we run from the CFC_WebApp directory. Let's make sure to manually add it to
# the python path so that we can keep our separation between the main code and
# the webapp layer

#Simple path that serves up a static landing page with javascript in it
@route('/')
def index():
  return static_file("index.html", static_path)

# Bunch of static pages that constitute our website
# Should we have gone for something like django instead after all?
# If this gets to be too much, we should definitely consider that
@route("/docs/<filename>")
def docs(filename):
  if filename != "privacy.html" and filename != "support.html" and filename != "about.html" and filename != "consent.html" and filename != "approval_letter.pdf":
    logging.error("Request for unknown filename "% filename)
    return HTTPError(404, "Don't try to hack me, you evil spammer")
  else:
    return static_file(filename, "%s/%s" % (static_path, "docs"))

@route("/<filename>")
def docs(filename):
  if filename != "privacy" and filename != "support" and filename != "about" and filename != "consent":
    return HTTPError(404, "Don't try to hack me, you evil spammer")
  else:
    return static_file("%s.html" % filename, "%s/%s" % (static_path, "docs"))

# Serve up the components of the webapp - library files, our javascript and css
# files, and HTML templates, properly
@route('/css/<filepath:path>')
def server_css(filepath):
    logging.debug("static filepath = %s" % filepath)
    return static_file(filepath, "%s/%s" % (static_path, "css"))

@route('/img/<filepath:path>')
def server_img(filepath):
    logging.debug("static filepath = %s" % filepath)
    return static_file(filepath, "%s/%s" % (static_path, "img"))

@route('/js/<filepath:path>')
def server_js(filepath):
    logging.debug("static filepath = %s" % filepath)
    return static_file(filepath, "%s/%s" % (static_path, "js"))

@route('/lib/<filepath:path>')
def server_lib(filepath):
    logging.debug("static filepath = %s" % filepath)
    return static_file(filepath, "%s/%s" % (static_path, "lib"))

@route('/templates/<filepath:path>')
def server_templates(filepath):
  logging.debug("static filepath = %s" % filepath)
  return static_file(filepath, "%s/%s" % (static_path, "templates"))

@route('/clients/<clientname>/front/<filename>')
def server_static(clientname, filename):
  logging.debug("returning file %s from client %s " % (filename, clientname))
  return static_file(filename, "clients/%s/%s" % (clientname, static_path))

# Returns the proportion of survey takers who use each mode
@route('/result/commute.modeshare.distance')
def getCommuteModeShare():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  return modeshare.get_Alluser_mode_share_by_distance("commute",
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # return modeshare.getModeShare()

@route('/result/internal.modeshare.distance')
def getBerkeleyModeShare():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  return Berkeley.get_berkeley_mode_share_by_distance(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # return modeshare.getModeShare()

# Returns the modeshare by zipcode
@route('/result/commute.modeshare/zipcode/<zc>')
def getCommuteModeShare(zc):
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  return zipcode.get_mode_share_by_Zipcode(zc, "commute",
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))

# Returns the proportion of survey takers from different zip codes
@route('/result/home.zipcode')
def getZipcode():
  return zipcode.getZipcode()

# Returns the proportion of commute distances
@route('/result/commute.distance.to')
def getDistance():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  distances = distance.get_morning_commute_distance_pie(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # logging.debug("Returning distances = %s" % distances)
  return distances

@route('/result/commute.distance.from')
def getDistance():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  distances = distance.get_evening_commute_distance_pie(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # logging.debug("Returning distances = %s" % distances)
  return distances

# Returns the distribution of commute arrival and departure times
@route('/result/commute.arrivalTime')
def getArrivalTime():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  retVal = work_time.get_Alluser_work_start_time_pie(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # retVal = common.generateRandomResult(['00-04', '04-08', '08-10'])
  # logging.debug("In getArrivalTime, retVal is %s" % retVal)
  return retVal

@route('/result/commute.departureTime')
def getDepartureTime():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  retVal = work_time.get_Alluser_work_end_time_pie(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # retVal = common.generateRandomResult(['00-04', '04-08', '08-10'])
  # logging.debug("In getDepartureTime, retVal is %s" % retVal)
  return retVal

@route("/result/heatmap/carbon")
def getCarbonHeatmap():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  retVal = visualize.carbon_by_zip(
    datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))
  # retVal = common.generateRandomResult(['00-04', '04-08', '08-10'])
  # logging.debug("In getCarbonHeatmap, retVal is %s" % retVal)
  return retVal

@post("/result/heatmap/pop.route")
def getPopRouteLegacy():
  return getPopRoute("local_date")

@post("/result/heatmap/pop.route/<time_type>")
def getPopRoute(time_type):
  if 'user' in request.json:
     user_uuid = getUUID(request)
  else:
     user_uuid = None

  if 'from_local_date' in request.json and 'to_local_date' in request.json:
      start_time = request.json['from_local_date']
      end_time = request.json['to_local_date']
  else:
      start_time = request.json['start_time']
      end_time = request.json['end_time']

  modes = request.json['modes']
  region = request.json['sel_region']
  logging.debug("Filtering values for user %s, range %s -> %s, region %s" %
        (user_uuid, start_time, end_time, region))
  time_type_map = {
      'timestamp': visualize.range_mode_heatmap_timestamp,
      'local_date': visualize.range_mode_heatmap_local_date
  }
  viz_fn = time_type_map[time_type]
  retVal = viz_fn(user_uuid, modes, start_time, end_time, region)
  return retVal

@post("/result/heatmap/incidents/<time_type>")
def getStressMap(time_type):
    if 'user' in request.json:
        user_uuid = getUUID(request)
    else:
        user_uuid = None

    # modes = request.json['modes']
    # hardcode modes to None because we currently don't store
    # mode information along with the incidents
    # we need to have some kind of cleaned incident that:
    # has a mode
    # maybe has a count generated from clustering....
    # but then what about times?
    modes = None
    if 'from_local_date' in request.json and 'to_local_date' in request.json:
        start_time = request.json['from_local_date']
        end_time = request.json['to_local_date']
    else:
        start_time = request.json['start_time']
        end_time = request.json['end_time']
    region = request.json['sel_region']
    logging.debug("Filtering values for %s, range %s -> %s, region %s" %
                  (user_uuid, start_time, end_time, region))
    time_type_map = {
        'timestamp': visualize.incident_heatmap_timestamp,
        'local_date': visualize.incident_heatmap_local_date
    }
    viz_fn = time_type_map[time_type]
    retVal = viz_fn(user_uuid, modes, start_time, end_time, region)
    # retVal = common.generateRandomResult(['00-04', '04-08', '08-10'])
    # logging.debug("In getCalPopRoute, retVal is %s" % retVal)
    return retVal

@post("/pipeline/get_complete_ts")
def getPipelineState():
    user_uuid = getUUID(request)
    return {"complete_ts": pipeline.get_complete_ts(user_uuid)}

@post("/datastreams/find_entries/<time_type>")
def getTimeseriesEntries(time_type):
    if 'user' not in request.json:
        abort(401, "only a user can read his/her data")

    user_uuid = getUUID(request)

    key_list = request.json['key_list']
    if 'from_local_date' in request.json and 'to_local_date' in request.json:
        start_time = request.json['from_local_date']
        end_time = request.json['to_local_date']
        time_query = esttc.TimeComponentQuery("metadata.write_ts",
                                              start_time,
                                              end_time)
    else:
        start_time = request.json['start_time']
        end_time = request.json['end_time']
        time_query = estt.TimeQuery("metadata.write_ts",
                                              start_time,
                                              end_time)
    # Note that queries from usercache are limited to 100,000 entries
    # and entries from timeseries are limited to 250,000, so we will
    # return at most 350,000 entries. So this means that we don't need
    # additional filtering, but this should be documented in
    # the API
    data_list = esdc.find_entries(user_uuid, key_list, time_query)
    return {'phone_data': data_list}

@get('/result/carbon/all/summary')
def carbonSummaryAllTrips():
  fromTs = request.query.from_ts
  toTs = request.query.to_ts
  logging.debug("Filtering values for range %s -> %s" % (fromTs, toTs))
  return carbon.getSummaryAllTrips(
      datetime.fromtimestamp(float(fromTs)/1000), datetime.fromtimestamp(float(toTs)/1000))

@get('/tripManager/getModeOptions')
def getModeOptions():
  return tripManager.getModeOptions()

@post('/tripManager/getUnclassifiedSections')
def getUnclassifiedSections():
  user_uuid=getUUID(request)
  return tripManager.getUnclassifiedSections(user_uuid)

@post('/tripManager/setSectionClassification')
def setSectionClassification():
  user_uuid=getUUID(request)
  updates = request.json['updates']
  return tripManager.setSectionClassification(user_uuid, updates)

@post('/tripManager/storeSensedTrips')
def storeSensedTrips():
  logging.debug("Called storeSensedTrips")
  user_uuid=getUUID(request)
  print "user_uuid %s" % user_uuid
  logging.debug("user_uuid %s" % user_uuid)
  sections = request.json['sections']
  return tripManager.storeSensedTrips(user_uuid, sections)

@post('/usercache/get')
def getFromCache():
  logging.debug("Called userCache.get")
  user_uuid=getUUID(request)
  logging.debug("user_uuid %s" % user_uuid)
  to_phone = usercache.sync_server_to_phone(user_uuid)
  return {'server_to_phone': to_phone}

@post('/usercache/put')
def putIntoCache():
  logging.debug("Called userCache.put")
  user_uuid=getUUID(request)
  logging.debug("user_uuid %s" % user_uuid)
  from_phone = request.json['phone_to_server']
  return usercache.sync_phone_to_server(user_uuid, from_phone)

@post('/timeline/getTrips/<day>')
def getTrips(day):
  logging.debug("Called timeline.getTrips/%s" % day)
  user_uuid=getUUID(request)
  force_refresh = request.query.get('refresh', False)
  logging.debug("user_uuid %s" % user_uuid)
  ret_geojson = timeline.get_trips_for_day(user_uuid, day, force_refresh)
  logging.debug("type(ret_geojson) = %s" % type(ret_geojson))
  ret_dict = {"timeline": ret_geojson}
  logging.debug("type(ret_dict) = %s" % type(ret_dict))
  return ret_dict

@post('/incidents/')

@post('/profile/create')
def createUserProfile():
  logging.debug("Called createUserProfile")
  userToken = request.json['user']
  # This is the only place we should use the email, since we may not have a
  # UUID yet. All others should only use the UUID.
  if skipAuth:
    userEmail = userToken
  else:
    userEmail = verifyUserToken(userToken)
  logging.debug("userEmail = %s" % userEmail)
  user = User.register(userEmail)
  logging.debug("Looked up user = %s" % user)
  logging.debug("Returning result %s" % {'uuid': str(user.uuid)})
  return {'uuid': str(user.uuid)}

@post('/profile/update')
def updateUserProfile():
  logging.debug("Called updateUserProfile")
  user_uuid = getUUID(request)
  user = User.fromUUID(user_uuid)
  new_fields = request.json['update_doc']
  return user.update(new_fields)

@post('/profile/get')
def getUserProfile():
  logging.debug("Called getUserProfile")
  user_uuid = getUUID(request)
  user = User.fromUUID(user_uuid)
  return user.getProfile()

@post('/profile/consent')
def setConsentInProfile():
  user_uuid = getUUID(request)
  version = request.json['version']
  print "Setting accepted version to %s for user %s" % (version, user_uuid)
  logging.debug("Setting accepted version to %s for user %s" % (version, user_uuid))
  return None

@post('/profile/settings')
def getCustomizationForProfile():
  user_uuid = getUUID(request)
  user = User.fromUUID(user_uuid)
  logging.debug("Returning settings for user %s" % user_uuid)
  return user.getSettings()

@post('/stats/set')
def setStats():
  user_uuid=getUUID(request)
  inStats = request.json['stats']
  stats.setClientMeasurements(user_uuid, inStats)

@post('/compare')
def postCarbonCompare():
  from clients.data import data
  from clients.choice import choice

  if not skipAuth:
      if request.json == None:
        return "Waiting for user data to become available..."
      if 'user' not in request.json:
        return "Waiting for user data to be become available.."

  user_uuid = getUUID(request)

  clientResult = userclient.getClientSpecificResult(user_uuid)
  if clientResult != None:
    logging.debug("Found overriding client result for user %s, returning it" % user_uuid)
    return clientResult
  else:
    logging.debug("No overriding client result for user %s, returning choice " % user_uuid)
  return choice.getResult(user_uuid)

@get('/compare')
def getCarbonCompare():
  for key, val in request.headers.items():
    print("  %s: %s" % (key, val))

  from clients.data import data

  if not skipAuth:
    if 'User' not in request.headers or request.headers.get('User') == '':
        return "Waiting for user data to become available..."

  from clients.choice import choice

  user_uuid = getUUID(request, inHeader=True)
  print ('UUID', user_uuid)

  clientResult = userclient.getClientSpecificResult(user_uuid)
  if clientResult != None:
    logging.debug("Found overriding client result for user %s, returning it" % user_uuid)
    return clientResult
  else:
    logging.debug("No overriding client result for user %s, returning choice" % user_uuid)
  return choice.getResult(user_uuid)

@post('/result/metrics/<time_type>')
def summarize_metrics(time_type):
    if 'user' in request.json:
        user_uuid = getUUID(request)
    else:
        user_uuid = None
    start_time = request.json['start_time']
    end_time = request.json['end_time']
    freq_name = request.json['freq']
    old_style = False
    if 'metric' in request.json:
        old_style = True
        metric_list = [request.json['metric']]
    else:
        metric_list = request.json['metric_list']

    logging.debug("metric_list = %s" % metric_list)

    if 'is_return_aggregate' in request.json:
        is_return_aggregate = request.json['is_return_aggregate']
    else:
        old_style = True
        is_return_aggregate = True
    time_type_map = {
        'timestamp': metrics.summarize_by_timestamp,
        'local_date': metrics.summarize_by_local_date
    }
    metric_fn = time_type_map[time_type]
    ret_val = metric_fn(user_uuid,
              start_time, end_time,
              freq_name, metric_list, is_return_aggregate)
    # logging.debug("ret_val = %s" % bson.json_util.dumps(ret_val))
    if old_style:
        logging.debug("old_style metrics found, returning array of entries instead of array of arrays")
        assert(len(metric_list) == 1)
        if 'user_metrics' in ret_val:
            ret_val['user_metrics'] = ret_val['user_metrics'][0]
        ret_val['aggregate_metrics'] = ret_val['aggregate_metrics'][0]
    return ret_val

@post('/join.group/<group_id>')
def habiticaJoinGroup(group_id):
    if 'user' in request.json:
        user_uuid = getUUID(request)
    else:
        user_uuid = None
    inviter_id = request.json['inviter']
    logging.debug("%s about to join party %s after invite from %s" %
                  (user_uuid, group_id, inviter_id))
    try:
        ret_val = habitproxy.setup_party(user_uuid, group_id, inviter_id)
        logging.debug("ret_val = %s after joining group" % bson.json_util.dumps(ret_val))
        return {'result': ret_val}
    except RuntimeError as e:
        logging.info("Aborting call with message %s" % e.message)
        abort(400, e.message)

# Pulling public data from the server
@get('/eval/publicData/timeseries')
def getPublicData():
  ids = request.json['phone_ids']
  all_uuids = map(lambda id: UUID(id), ids)
  uuids = [uuid for uuid in all_uuids if uuid in estag.TEST_PHONE_IDS]

  from_ts = request.query.from_ts
  to_ts = request.query.to_ts

  time_range = estt.TimeQuery("metadata.write_ts", float(from_ts), float(to_ts))
  time_query = time_range.get_query()

  user_queries = map(lambda id: {'user_id': id}, uuids)

  for q in user_queries:
    q.update(time_query)

  num_entries_ts = map(lambda q: edb.get_timeseries_db().find(q).count(), user_queries)
  num_entries_uc = map(lambda q: edb.get_usercache_db().find(q).count(), user_queries)
  total_entries = sum(num_entries_ts + num_entries_uc)
  logging.debug("Total entries requested: %d" % total_entries)

  threshold = 200000
  if total_entries > threshold:
    data_list = None
  else:
    data_list = map(lambda u: esdc.find_entries(u, None, time_range), all_uuids)

  return {'phone_data': data_list}

# Redirect to custom URL. $%$%$$ gmail
@get('/redirect/<route>')
def getCustomURL(route):
  print route
  print urllib.urlencode(request.query)
  logging.debug("route = %s, query params = %s" % (route, request.query))
  if route == "join":
    redirected_url = "/#/setup?%s" % (urllib.urlencode(request.query))
  else:
    redirected_url = 'emission://%s?%s' % (route, urllib.urlencode(request.query))
  response.status = 303
  response.set_header('Location', redirected_url)
  # response.set_header('Location', 'mailto://%s@%s' % (route, urllib.urlencode(request.query)))
  logging.debug("Redirecting to URL %s" % redirected_url)
  print("Redirecting to URL %s" % redirected_url)
  return {'redirect': 'success'}


# Client related code START
@post("/client/<clientname>/<method>")
def callStudy(clientname, method):
  user_uuid = getUUID(request)
  request['user'] = user_uuid
  return Client(clientname).callMethod(method, request)

@get('/client/pre-register')
def registeredForStudy():
  userEmail = request.query.email
  client = request.query.client
  client_key = request.query.client_key

  logging.debug("request = %s" % (request))
  logging.debug("userEmail = %s, client = %s, client_key = %s" % (userEmail, client, client_key))
  # try:
  newSignupCount = Client(client).preRegister(client_key, userEmail)
  # except Exception as e:
  #   abort(e.code, e.msg)
  return {'email': userEmail, 'client': client, 'signup_count': newSignupCount }

@get('/client/<clientName>/<method>')
def javascriptCallback(clientName, method):
  from clients.choice import choice

  client = Client(clientName)
  client_key = request.query.client_key
  client.callJavascriptCallback(client_key, method, request.params)
  return {'status': 'ok'}

# proxy used to request and process XML from an external API, then convert it to JSON
# original URL should be encoded in UTF-8
@get("/asJSON/<originalXMLWebserviceURL>")
def xmlProxy(originalXMLWebserviceURL):
  decodedURL = urllib2.unquote(originalXMLWebserviceURL)
  f = urllib2.urlopen(decodedURL)
  xml = f.read()
  parsedXML = xmltodict.parse(xml)
  return json.dumps(parsedXML)

# Client related code END

# Data source integration START
@post('/movesCallback')
def movesCallback():
  logging.debug("Request from user = %s" % request)
  logging.debug("Request.json from user = %s" % request.json)
  user_uuid = getUUID(request)
  if user_uuid is None:
    # Hack to support older clients that don't call register before calling movesCallback
    # Remove by Dec 31, 2014
    createUserProfile()
    user_uuid = getUUID(request)
  assert(user_uuid is not None)
  code = request.json['code']
  state = request.json['state']
  return auth.movesCallback(code, state, user_uuid)

@post('/habiticaRegister')
def habiticaRegister():
  logging.debug("habitica registration request %s from user = %s" %
                (request.json, request))
  user_uuid = getUUID(request)
  assert(user_uuid is not None)
  username = request.json['regConfig']['username']
  # TODO: Move this logic into register since there is no point in
  # regenerating the password if we already have the user
  autogen_id = requests.get("http://www.dinopass.com/password/simple").text
  logging.debug("generated id %s through dinopass" % autogen_id)
  autogen_email = "%s@save.world" % autogen_idf
  autogen_password = autogen_id
  return habitproxy.habiticaRegister(username, autogen_email,
                              autogen_password, user_uuid)

@post('/habiticaProxy')
def habiticaProxy():
    logging.debug("habitica registration request %s" % (request))
    user_uuid = getUUID(request)
    assert(user_uuid is not None)
    method = request.json['callOpts']['method']
    method_url = request.json['callOpts']['method_url']
    method_args = request.json['callOpts']['method_args']
    return habitproxy.habiticaProxy(user_uuid, method, method_url,
                                    method_args)
# Data source integration END

# Survey integration START
@get('/survey')
def saveSurvey():
    logging.debug("Survey saving request %s" % (request))
    # user_uuid = getUUID(request)
    # assert (user_uuid is not None)

    return {'status': 'ok', 'test': 'Hello World!'}
# Survey integration END


@app.hook('before_request')
def before_request():
  print("START %s %s %s" % (datetime.now(), request.method, request.path))
  request.params.start_ts = time.time()
  request.params.timer = ect.Timer()
  request.params.timer.__enter__()
  logging.debug("START %s %s" % (request.method, request.path))

@app.hook('after_request')
def after_request():
  msTimeNow = time.time()
  request.params.timer.__exit__()
  duration = msTimeNow - request.params.start_ts
  new_duration = request.params.timer.elapsed
  if round((duration - new_duration) / new_duration > 100) > 0:
    logging.error("old style duration %s != timer based duration %s" % (duration, new_duration))
    stats.store_server_api_error(request.params.user_uuid, "MISMATCH_%s_%s" %
                                 (request.method, request.path), msTimeNow, duration - new_duration)

  print("END %s %s %s %s %s " % (datetime.now(), request.method, request.path, request.params.user_uuid, duration))
  logging.debug("END %s %s %s %s " % (request.method, request.path, request.params.user_uuid, duration))
  # Keep track of the time and duration for each call
  stats.store_server_api_time(request.params.user_uuid, "%s_%s" % (request.method, request.path),
        msTimeNow, duration)
  stats.store_server_api_time(request.params.user_uuid, "%s_%s_cputime" % (request.method, request.path),
        msTimeNow, new_duration)

# Auth helpers BEGIN
# This should only be used by createUserProfile since we may not have a UUID
# yet. All others should use the UUID.
def verifyUserToken(token):
    tokenFields = tokenValidator.verify_and_decode_token(token)
    return tokenFields['email']

def getUUIDFromToken(token):
    userEmail = verifyUserToken(token)
    return __getUUIDFromEmail__(userEmail)

# This should not be used for general API calls
def __getUUIDFromEmail__(userEmail):
    user=User.fromEmail(userEmail)
    if user is None:
        return None
    user_uuid=user.uuid
    return user_uuid

def __getToken__(request, inHeader):
    if inHeader:
      userHeaderSplitList = request.headers.get('User').split()
      if len(userHeaderSplitList) == 1:
          userToken = userHeaderSplitList[0]
      else:
          userToken = userHeaderSplitList[1]
    else:
      userToken = request.json['user']

    return userToken

def getUUID(request, inHeader=False):
  retUUID = None
  if skipAuth:
    if 'User' in request.headers or 'user' in request.json:
        # skipAuth = true, so the email will be sent in plaintext
        userEmail = __getToken__(request, inHeader)
        retUUID = __getUUIDFromEmail__(userEmail)
        logging.debug("skipAuth = %s, returning UUID directly from email %s" % (skipAuth, retUUID))
    else:
        logging.debug("skipAuth = %s, returning None")
        return None
    if Client("choice").getClientKey() is None:
        Client("choice").update(createKey = True)
  else:
    userToken = __getToken__(request, inHeader)
    retUUID = getUUIDFromToken(userToken)
  if retUUID is None:
     raise HTTPError(403, "token is valid, but no account found for user")
  request.params.user_uuid = retUUID
  return retUUID
# Auth helpers END

if __name__ == '__main__':
    try:
        webserver_log_config = json.load(open("conf/log/webserver.conf", "r"))
    except:
        webserver_log_config = json.load(open("conf/log/webserver.conf.sample", "r"))

    logging.config.dictConfig(webserver_log_config)
    logging.debug("This should go to the log file")

    # We have see the sockets hang in practice. Let's set the socket timeout = 1
    # hour to be on the safe side, and see if it is hit.
    socket.setdefaulttimeout(float(socket_timeout))

    for plugin in app.plugins:
        if isinstance(plugin, JSONPlugin):
            print("Replaced json_dumps in plugin with the one from bson")
            plugin.json_dumps = bson.json_util.dumps

    print("Changing bt.json_loads from %s to %s" % (bt.json_loads, bson.json_util.loads))
    bt.json_loads = bson.json_util.loads

    # The selection of SSL versus non-SSL should really be done through a config
    # option and not through editing source code, so let's make this keyed off the
    # port number
    if server_port == "443":
      # We support SSL and want to use it
      run(host=server_host, port=server_port, server='cherrypy', debug=True,
          certfile=ssl_cert, keyfile=private_key, ssl_module='builtin')
    else:
      # Non SSL option for testing on localhost
      # We can theoretically use a separate skipAuth flag specified in the config file,
      # but then we have to define the behavior if SSL is true and we are not
      # running on localhost but still want to run without authentication. That is
      # not really an important use case now, and it makes people have to change
      # two values and increases the chance of bugs. So let's key the auth skipping from this as well.
      # skipAuth = True
      # print "Running with HTTPS turned OFF, skipAuth = True"

      run(host=server_host, port=server_port, server='cherrypy', debug=True)

    # run(host="0.0.0.0", port=server_port, server='cherrypy', debug=True)
