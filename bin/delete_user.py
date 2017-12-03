from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from future import standard_library
standard_library.install_aliases()
from builtins import *
from pymongo import MongoClient
from get_database import get_uuid_db, get_profile_db, get_moves_db
from uuid import UUID
from dao.user import User
from main import auth
import sys

def deleteUser(userEmail):
  deluuid = User.unregister(userEmail)
  auth.deleteAllTokens(deluuid)

if __name__ == '__main__':
  if len(sys.argv) != 2:
    print("USAGE: delete_user.py <userEmail>")
    exit(1)

  userEmail = sys.argv[1]
  print("Deleting user %s" % userEmail)
  deleteUser(sys.argv[1])
