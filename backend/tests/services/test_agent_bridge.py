import asyncio,base64,hashlib,hmac,json,time
import pytest
from quantum_backend_v2.api.deps.auth import _resolve_user_claims,require_authenticated,configure_auth
from quantum_backend_v2.api.errors.models import PlatformException

def token(key,**overrides):
 now=int(time.time());p={'sub':'user-123','email':'user@example.test','iat':now,'exp':now+60,'aud':'quantumnodes-agentkit',**overrides}
 body=base64.urlsafe_b64encode(json.dumps(p).encode()).rstrip(b'=').decode()
 return 'qn1.'+body+'.'+hmac.new(key.encode(),body.encode(),hashlib.sha256).hexdigest()

def test_bridge_identity_survives_development_bypass(monkeypatch):
 key='k'*32;monkeypatch.setenv('AGENT_AUTH_BRIDGE_SECRET',key);configure_auth(enabled=False)
 try:
  async def run():
   claims=await _resolve_user_claims('Bearer '+token(key));return await require_authenticated(claims)
  claims=asyncio.run(run());assert claims.user_id=='user-123';assert not claims.is_admin()
 finally:configure_auth(enabled=True)

@pytest.mark.parametrize('overrides',[{'exp':1},{'aud':'other'},{'iat':int(time.time())+500},{'exp':int(time.time())+9999}])
def test_rejects_invalid_claims_even_with_dev_bypass(monkeypatch,overrides):
 monkeypatch.setenv('AGENT_AUTH_BRIDGE_SECRET','k'*32);configure_auth(enabled=False)
 try:
  with pytest.raises(PlatformException):asyncio.run(_resolve_user_claims('Bearer '+token('k'*32,**overrides)))
 finally:configure_auth(enabled=True)

def test_rejects_tampered_signature(monkeypatch):
 monkeypatch.setenv('AGENT_AUTH_BRIDGE_SECRET','k'*32)
 with pytest.raises(PlatformException):asyncio.run(_resolve_user_claims('Bearer '+token('wrong-key')))
