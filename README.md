# udata-front-kit-seo

Génère un `sitemap.xml` et un `robots.txt` pour un couple site (verticale) / environnement.

Utilise la configuration du site/env stockée sur le github de `udata-front-kit` pour récupérer les urls à inclure dans le `sitemap.xml` et les règles du `robots.txt`.

Envoie les fichiers vers un bucket S3.

Genère toujours un `sitemap.xml` (peut être une liste vide) et un `robots.txt`, sauf en cas de crash du script.

## Configuration distante

```yaml
website:
  seo:
    canonical_url: https://site.data.gouv.fr
    meta:
      keywords: 'mots-clés, séparés, par, virgules'
      description: 'Description du site'
      robots: 'index, follow' # 'noindex, nofollow' pour demo/preprod
    robots_txt:
      disallow:
        - /admin
    sitemap_xml:
      topics_pages:
        - bouquets
      datasets_pages:
        - indicators
      dataservices_pages:
        - dataservices
```

## Variables d'environnement attendues

- `ENV` : environnement cible `(demo|preprod|prod)`
- `SITE` : site (verticale) cible. NB: `ecologie` est implicitement converti en `ecospheres` lorsque nécessaire.
- `AWS_ACCESS_KEY_ID` : utilisateur S3
- `AWS_SECRET_ACCESS_KEY` : mot de passe S3
- `AWS_ENDPOINT_URL` : url S3
- `AWS_BUCKET` : bucket S3 cible (défaut `ufk`)

## Stockage S3

Le stockage se fait sous cette forme :

```
ufk
└── ecologie
    ├── demo
    │   ├── robots.txt
    │   └── sitemap.xml
    └── prod
        ├── robots.txt
        └── sitemap.xml
```

## Exécution avec docker

```shell
docker build -t udata-front-kit-seo .
docker run -e ENV=demo -e SITE=ecologie -e AWS_ENDPOINT_URL=https://s3.example.com -e AWS_ACCESS_KEY_ID=key -e AWS_SECRET_ACCESS_KEY=secret udata-front-kit-seo
```

## Déploiement

Le script et son environnement d'exécution sont déployés par data.gouv.fr.
