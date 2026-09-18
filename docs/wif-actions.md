# Correr en Actions contra Vertex, sin ninguna clave

> **Estado (2026-09-18): no se ha dado de alta, y se ha decidido no pedirlo.** La
> cuenta disponible no tiene `iam.workloadIdentityPools.create`, y en vez de tramitar
> permisos se ha optado por seguir corriendo en local con `gcloud auth login`,
> renovando la sesion cuando caduca — las tandas esperan en vez de morir y se reanudan
> sin re-pagar (`src/dr/llm.py`, `experiments/adjudicar.py`).
>
> El workflow conserva el camino de WIF, con `provider: auto` por defecto para que
> nadie se lo encuentre fallando. Este documento queda como receta lista por si algun
> dia interesa: el coste de la decision es una intervencion manual cada pocas horas en
> las rejillas largas.

El spec (decisión 4) dice que las rejillas van en GitHub Actions y no en el portátil:
son espera contra una API, la máquina local se satura y ya se perdieron tandas por eso.
Lo que impedía cumplirlo con Vertex era la autenticación, y esto lo resuelve.

## Por qué no vale `gcloud auth login`

La sesión SSO de gcloud caduca cada pocas horas. En una sola sesión de trabajo tumbó
tres tandas, cada una a mitad de celda:

- el **token** caduca al minuto sesenta — eso lo arregla el cliente pidiendo otro;
- la **credencial** caduca entera al cabo de unas horas, y ahí `gcloud auth
  print-access-token` falla con `Reauthentication failed. cannot prompt during
  non-interactive execution`. No hay reintento que valga: hace falta un navegador.

Una cuenta de servicio con clave JSON lo evitaría, pero deja un secreto en disco y en
los secretos del repo, que es justo lo que el backend de Vertex vino a no hacer.

## Workload Identity Federation: qué es el secreto aquí

Ninguno. GitHub firma un token OIDC que dice «este job viene del repo
`JaviMaligno/delayed-relevance`»; GCP se lo cree porque hemos declarado que confía en
esa identidad, y devuelve una credencial de vida corta que muere con el job. No hay
clave que rotar, ni que filtrar, ni que caduque a media rejilla.

## Alta (una vez, con `gcloud auth login` hecho)

```bash
PROJECT=data-science-364702
NUMERO=$(gcloud projects describe $PROJECT --format='value(projectNumber)')
REPO=JaviMaligno/delayed-relevance

gcloud iam workload-identity-pools create github --project=$PROJECT \
  --location=global --display-name="GitHub Actions"

# `attribute-condition` es obligatorio y no es burocracia: sin él, el proveedor
# acepta tokens de CUALQUIER repositorio de GitHub.
gcloud iam workload-identity-pools providers create-oidc github-oidc \
  --project=$PROJECT --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository=='$REPO'"

gcloud iam service-accounts create dr-experimentos --project=$PROJECT \
  --display-name="Rejillas de delayed-relevance"

# Solo lo que hace falta para inferir. Nada de editor.
gcloud projects add-iam-policy-binding $PROJECT \
  --member="serviceAccount:dr-experimentos@$PROJECT.iam.gserviceaccount.com" \
  --role=roles/aiplatform.user

# Quién puede hacerse pasar por esa cuenta: solo este repositorio.
gcloud iam service-accounts add-iam-policy-binding \
  dr-experimentos@$PROJECT.iam.gserviceaccount.com --project=$PROJECT \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/$NUMERO/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

# Variables del repo (no secretos: no hay nada que ocultar).
gh variable set GCP_PROJECT --repo $REPO --body "$PROJECT"
gh variable set GCP_SERVICE_ACCOUNT --repo $REPO \
  --body "dr-experimentos@$PROJECT.iam.gserviceaccount.com"
gh variable set GCP_WIF_PROVIDER --repo $REPO \
  --body "projects/$NUMERO/locations/global/workloadIdentityPools/github/providers/github-oidc"
```

**Permisos necesarios para dar el alta**: `roles/editor` **no basta** —no incluye
`setIamPolicy`—. Hace falta `roles/iam.workloadIdentityPoolAdmin`,
`roles/iam.serviceAccountAdmin` y `roles/resourcemanager.projectIamAdmin`, o que lo
ejecute alguien con `roles/owner`.

## Comprobación

Lanzar el workflow con `provider: vertex` y el horizonte más barato:
`experimento=table1`, `model=gemini-3-flash-preview`, `horizons=10`, `seeds=1`.
El paso de comprobación imprime `credencial de GCP operativa` antes de gastar un euro;
si WIF no está bien dado de alta, falla ahí y no a los dos minutos de rejilla.
