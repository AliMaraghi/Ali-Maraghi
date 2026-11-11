"""Owner-session-bound OAuth controller; production HTTP mounting is gated.

Caller supplies an already authenticated owner session, never an arbitrary request
header. No deployment or session authentication is implied by these methods.
"""
from .google_oauth_state import bounded
from .google_token_http import exchange
from .google_http import GmailClient
from .kernel.policy import enforce_durable_stop


class GoogleConnection:
    def __init__(self, state, broker, client_secret):
        if state.owner != broker.owner or state.ledger is not broker.ledger or state.client_id != broker.client_id:
            raise ValueError('OAuth and credentials must share owner and Ledger')
        self.state, self.broker = state, broker
        self.client_secret = bounded(client_secret,1,4096)

    def begin(self, authenticated_owner, session):
        if authenticated_owner != self.state.owner:raise PermissionError('Owner required')
        return self.state.begin(session,['gmail'])

    def callback(self, authenticated_owner, session, state, code):
        if authenticated_owner != self.state.owner:raise PermissionError('Owner required')
        bounded(code,1,4096)
        # Consume state before remote exchange; ambiguous failures require new consent.
        material=self.state.consume(state,session)
        enforce_durable_stop(self.broker.ledger)
        response=exchange({'client_id':self.state.client_id,'client_secret':self.client_secret,
            'grant_type':'authorization_code','code':code,'code_verifier':material['code_verifier'],
            'redirect_uri':material['redirect_uri']})
        # Validate token shape/scope before using it and bind actual Gmail identity.
        normalized=self.broker._normalized(response)
        client=GmailClient(self.broker.ledger,self.broker.owner,self.broker.policy,
                           lambda:normalized['access_token'])
        profile=client.get('profile',{})
        self.broker.install(response,profile.get('emailAddress'))
        return self.broker.status()

    def token(self):
        return self.broker.access_token(lambda refresh:exchange({
            'client_id':self.state.client_id,'client_secret':self.client_secret,
            'grant_type':'refresh_token','refresh_token':refresh}))

    def client(self):
        return GmailClient(self.broker.ledger,self.broker.owner,self.broker.policy,self.token)
