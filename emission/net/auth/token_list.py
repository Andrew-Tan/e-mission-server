import logging
import json
import traceback
import requests

# For decoding JWTs on the client side
import oauth2client.client
from oauth2client.crypt import AppIdentityError

class TokenListMethod:
    def __init__(self):
        key_file = open('conf/net/keys.json')
        key_data = json.load(key_file)
        self.token_list_file = key_data["token_list"]
        raw_token_list = open(self.token_list_file).readlines()
        self.token_list = [t.strip() for t in raw_token_list]
        raw_token_list = None

    def verifyUserToken(self, token):
        # attempt to validate token on the client-side
        logging.debug("Using the TokenListMethod to verify id token of length %d " % 
            len(token))
        matching_list = [token == curr_token for curr_token in self.token_list]
        print matching_list
        stripped_matching_list = [token == curr_token.strip() for curr_token in self.token_list]
        print stripped_matching_list
        if token in self.token_list:
            logging.debug("Found match for token %s of length %d" % (token, len(token)))
            # In this case, the token is the email, since we don't actually
            # have the user email
            return token
        else:
            raise ValueError("Invalid token %s, not found in list of length %d" % 
                (token, len(self.token_list)))
