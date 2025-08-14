# ecospheres-sitemap

Génère le sitemap pour ecologie.data.gouv.fr en utilisant l'API publique de data.gouv.fr.

- Récupère les `Topic` taggués `univers-ecospheres`.
- Récupère les `Dataset` correspondant aux indicateurs territoriaux.
- Construit un sitemap avec :
    - les `Topic` récupérés plus haut, la date de dernière modification est celle du `Topic`,
    - les `Dataset` récupérés plus haut, la date de dernière modification est celle du `Dataset`,
    - les pages statiques indiquées dans `STATIC_URLS`, la date de dernière modification est celle du header `last-modified`.
- Publie sur s3 le `sitemap.xml` si l'accès S3 est configuré.

## Exécution avec docker

```shell
docker build -t ecospheres-sitemap .
docker run -e ENV=demo -e AWS_ENDPOINT_URL=https://s3.example.com -e AWS_ACCESS_KEY_ID=key -e AWS_SECRET_ACCESS_KEY=secret ecospheres-sitemap
```

## Déploiement

Le script et son environnement d'exécution sont déployés par data.gouv.fr au déploiement de ecologie.data.gouv.fr.
