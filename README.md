# DataVortex AI — Cloud Backend

## O que já está implementado
- FastAPI backend
- PostgreSQL real via SQLAlchemy + Alembic
- JWT authentication
- Multi-tenant por `org_id`
- Upload e persistência de transações CSV
- Analytics financeiros no servidor
- OpenAI Responses API para análise financeira, quando `OPENAI_API_KEY` estiver configurada
- Stripe Checkout para assinatura + webhook de atualização de plano
- Plaid Link Token + estrutura para sincronização bancária
- Docker Compose para ambiente local
- Render blueprint para deploy do backend
- Frontend mínimo de conexão

## Rodar localmente
1. Copie `.env.example` para `.env`.
2. Gere um SECRET_KEY forte.
3. `docker compose up --build`
4. Em outro terminal: `docker compose exec api alembic upgrade head`
5. API: http://localhost:8000/docs

## Produção
Configure as variáveis secretas no provedor cloud e um PostgreSQL gerenciado. O `render.yaml` serve como ponto de partida.

## Integrações
OpenAI usa a Responses API no servidor e `store=false` no exemplo.
Stripe usa Checkout em modo subscription e webhook.
Plaid usa Transactions e Link; produção exige credenciais/aprovação da conta Plaid.

## Segurança
- Nunca coloque chaves de OpenAI, Stripe ou Plaid no frontend.
- Use HTTPS.
- Troque SECRET_KEY.
- Configure CORS para o domínio real.
- Para tokens bancários em produção, use KMS/secret manager e criptografia em repouso.
- Antes de operar com dados financeiros reais, implemente auditoria, rate limiting, gestão de sessões, rotação de segredos, backups, observabilidade e revisão de compliance/regulação aplicável.
