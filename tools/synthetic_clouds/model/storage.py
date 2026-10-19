"""A POSTURA PUBLICADA de um bucket S3 -- o Incremento 3 do catalogo de postura.

Este Incremento 2 carregou as REGRAS dos security groups da AWS. O Incremento 3 faz o
mesmo pelos BUCKETS: ate aqui os 15 recursos ``s3_bucket`` existiam e eram inventariados
e faturados, mas o estate nao carregava a POSTURA que as chamadas de configuracao
publicam -- ACL, bucket policy e public access block -- e as tres regras de Config sobre
exposicao publica respondiam ``INSUFFICIENT_DATA`` por lacuna de modelo nomeada.

**Por que uma colecao a parte, e nao uma coluna em ``Resource``.** ``Resource`` e o
portador de identidade que a FOCUS 1.2 consome coluna a coluna; nenhum elemento da
documentacao do S3 faz parte daquele conjunto, e acrescentar um tornaria o portador
carregar um dado que nenhum consumidor de billing tem. A postura fica entao numa
colecao propria do estate, keyed pelo ``resource_uuid`` do bucket -- exatamente como
``Estate.aws_security_groups`` faz com os grupos.

**O que cada dataclass espelha.** Cada uma existe porque a pagina de documentacao a
publica como um tipo nomeado:

* :class:`AwsAclOwner` -- o ``Owner`` de ``API_Owner.md``.
* :class:`AwsBucketGrant` -- um ``Grant`` de ``API_Grant.md``: um ``Grantee``
  (``API_Grantee.md``) mais o ``Permission``.
* :class:`AwsPublicAccessBlock` -- os quatro booleanos de
  ``API_PublicAccessBlockConfiguration.md``.
* :class:`AwsPolicyStatement` / :class:`AwsBucketPolicy` -- o documento que
  ``GetBucketPolicy`` devolve em ``Policy``, cujos membros aparecem na resposta de
  exemplo da propria pagina da API.
* :class:`AwsBucketPosture` -- a postura de UM bucket, e a chave que as tres chamadas
  por bucket leem.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Os URIs dos grupos PREDEFINIDOS que a AWS publica como "public", verbatim da pagina
#: "Who is a grantee?" (``acl-overview.md``). O teste de publicacao que a propria AWS
#: escreve e sobre estes dois nomes: "Amazon S3 considers a bucket or object ACL public
#: if it grants any permissions to members of the predefined ``AllUsers`` or
#: ``AuthenticatedUsers`` groups". Eles moram no MODEL, e nao em ``generate/constants``,
#: porque sao identificadores documentados -- o mesmo motivo de ``AWS_ID_PREFIXES``
#: estar em ``model/identity.py``.
S3_ALL_USERS_URI = "http://acs.amazonaws.com/groups/global/AllUsers"
S3_AUTHENTICATED_USERS_URI = "http://acs.amazonaws.com/groups/global/AuthenticatedUsers"

#: Os dois grupos que a definicao acima chama de public, na ordem em que aparecem na frase.
S3_PUBLIC_GROUP_URIS: tuple[str, ...] = (S3_ALL_USERS_URI, S3_AUTHENTICATED_USERS_URI)

#: O grupo de entrega de logs, verbatim da mesma pagina. NAO e um dos dois grupos publicos
#: -- a definicao da AWS nomeia so ``AllUsers`` e ``AuthenticatedUsers`` -- entao um grant
#: para o LogDelivery group mantem o bucket nao-publico, que e o que a canned ACL
#: ``log-delivery-write`` da mesma tabela descreve.
S3_LOG_DELIVERY_URI = "http://acs.amazonaws.com/groups/s3/LogDelivery"

#: As permissoes de ACL que a tabela de canned ACLs associa a leitura/escrita. A mesma
#: tabela diz que ``public-read`` da ``READ`` ao grupo AllUsers e que
#: ``public-read-write`` da ``READ`` e ``WRITE``, entao o par publico de leitura e
#: {READ, READ_ACP} e o de escrita e {WRITE, WRITE_ACP} -- ``FULL_CONTROL`` concede as
#: duas e por isso e publico nas duas direcoes.
S3_PUBLIC_READ_PERMISSIONS = frozenset({"READ", "READ_ACP", "FULL_CONTROL"})
S3_PUBLIC_WRITE_PERMISSIONS = frozenset({"WRITE", "WRITE_ACP", "FULL_CONTROL"})


@dataclass(slots=True, frozen=True)
class AwsAclOwner:
    """O ``Owner`` de um ``AccessControlPolicy`` -- ``API_Owner.md``.

    A pagina publica ``DisplayName`` e ``ID``, ambos ``Required: No``. O owner e o
    mesmo nas duas respostas que o carregam (``ListBuckets`` e ``GetBucketAcl``), entao
    o estate guarda UM owner por bucket e os dois renderers leem o mesmo objeto.
    """

    display_name: str | None
    id: str


@dataclass(slots=True, frozen=True)
class AwsBucketGrant:
    """Um ``Grant`` do ``AccessControlList`` -- ``API_Grant.md``.

    ``permission`` e ``grantee_type`` sao os dois membros que a pagina restringe a
    valores nomeados (``FULL_CONTROL | WRITE | WRITE_ACP | READ | READ_ACP`` e
    ``CanonicalUser | AmazonCustomerByEmail | Group``). Os outros quatro membros do
    ``Grantee`` sao ``Required: No`` e ficam em ``None`` quando o grant nao os usa --
    um grant de grupo carrega so ``uri``, um grant de usuario canonico so ``id``.
    """

    permission: str
    grantee_type: str
    display_name: str | None = None
    email_address: str | None = None
    grantee_id: str | None = None
    uri: str | None = None


@dataclass(slots=True, frozen=True)
class AwsPublicAccessBlock:
    """O ``PublicAccessBlockConfiguration`` de um bucket -- ``API_PublicAccessBlockConfiguration.md``.

    Os quatro membros sao ``Type: Boolean`` e ``Required: No``; os quatro booleanos
    ficam no estate mesmo quando nao ha block configurado, porque um bucket sem
    configuracao tem os quatro em ``False``, que e a leitura que as regras de Config
    fazem.
    """

    block_public_acls: bool
    ignore_public_acls: bool
    block_public_policy: bool
    restrict_public_buckets: bool

    @property
    def restricts_public_acls(self) -> bool:
        """``True`` quando o ``BlockPublicAcls`` esta ligado.

        E o membro que a pagina do ``GetPublicAccessBlock`` descreve como "block public
        access control lists (ACLs) for this bucket", e portanto o que as regras
        ``s3-bucket-public-*-prohibited`` chamam de "the Block Public Access setting
        restricts public ACLs".
        """
        return self.block_public_acls

    @property
    def restricts_public_policies(self) -> bool:
        """``True`` quando o ``BlockPublicPolicy`` esta ligado.

        E o membro que a mesma pagina descreve como "block public bucket policies for
        this bucket" -- o "restricts public policies" das duas regras.
        """
        return self.block_public_policy


@dataclass(slots=True, frozen=True)
class AwsPolicyStatement:
    """Um item do ``Statement`` de uma bucket policy.

    Os membros sao os que a RESPOSTA DE EXEMPLO da pagina ``API_GetBucketPolicy.md``
    mostra num statement: ``Sid``, ``Effect``, ``Principal``, ``Action`` e ``Resource``.
    ``Action`` e ``Resource`` sao publicados como escalar OU lista -- o exemplo traz
    ``"Action":["s3:*"]`` com ``"Resource":"arn:aws:s3:::bucket/*"`` escalar -- e aqui
    os dois sao tuplas, com um elemento quando a politica escreve o escalar.
    """

    effect: str
    actions: tuple[str, ...]
    principals: tuple[str, ...]
    resources: tuple[str, ...]
    sid: str | None = None


@dataclass(slots=True, frozen=True)
class AwsBucketPolicy:
    """O documento que ``GetBucketPolicy`` devolve em ``Policy``.

    ``Version`` e ``Statement`` sao os dois membros que a resposta de exemplo mostra em
    qualquer statement; ``policy_id`` carrega o ``Id`` do documento, tambem publicado
    no mesmo exemplo.
    """

    version: str
    statements: tuple[AwsPolicyStatement, ...]
    policy_id: str | None = None


@dataclass(slots=True, frozen=True)
class AwsRegionalAccessBlock:
    """O Block Public Access DE REGIÃO de um bucket -- o par ``Region``/``RegionPrefix``.

    ESTE TIPO NAO ESTA NO CONTRATO DAS DUAS ACOES PUBLICADAS
    --------------------------------------------------------
    Medido em 2026-10-18 sobre ``API_GetPublicAccessBlock.html`` e
    ``API_PutPublicAccessBlock.html``: ``RegionalAccessBlockConfiguration`` tem ZERO
    ocorrencias nas duas paginas, e o ``PublicAccessBlockConfiguration`` que elas documentam
    tem quatro membros, nenhum deles regional. O bloco por regiao existe na API, e os SDKs o
    publicam, mas a referencia publica consultada nao o descreve.

    Por isso ele mora aqui como um tipo SEPARADO e nao como um quinto membro de
    :class:`AwsPublicAccessBlock`: um membro a mais no tipo publicado seria uma coluna que o
    auditor de conjunto acusaria de inventada, e o efeito real de um tipo separado e que a
    ausencia fica VISIVEL -- a configuracao regional e ``None`` quando a conta nao a definiu,
    e o renderer publica essa ausencia num artefato irmao, marcado como nao comprovado.

    ``region_id`` e ``region_prefix`` sao os dois membros de LOCALIZACAO: a regiao nomeada e o
    prefixo, que e o que permite bloquear um conjunto de regioes de uma vez. Os quatro
    interruptores sao os mesmos de :class:`AwsPublicAccessBlock`, e a combinacao MAIS
    RESTRITIVA entre o bloco do bucket e o da regiao e o que o S3 aplica -- combinacao que a
    pagina de GetPublicAccessBlock descreve para o nivel de CONTA e que, aqui, fica com a
    mesma forma porem com o par bucket/regiao.
    """

    region_id: str
    region_prefix: str
    block_public_acls: bool
    ignore_public_acls: bool
    block_public_policy: bool
    restrict_public_buckets: bool


@dataclass(slots=True, frozen=True)
class AwsBucketPosture:
    """A postura de UM bucket S3 -- a chave que as tres chamadas por bucket leem.

    ``acl_grants`` e a ACL ARMAZADA. O ``GetBucketAcl`` publica a ACL EFETIVA, e a
    pagina ``access-control-block-public-access`` e explicita a diferenca: "Calls to
    GetBucketAcl ... always return the effective permissions in place for the specified
    bucket ... suppose that a bucket has an ACL that grants public access, but the
    bucket also has the IgnorePublicAcls setting enabled. In this case, GetBucketAcl
    returns an ACL that reflects the access permissions that Amazon S3 is enforcing,
    rather than the actual ACL". Guardar as duas e o que permite ao renderer publicar a
    efativa sem mentir sobre a armazenada -- e e o que faz um bucket ``IgnorePublicAcls``
    responder ``private`` para ``GetBucketAcl`` enquanto ``RestrictPublicBuckets`` ainda
    aparece ligado.

    ``policy`` e ``None`` quando o bucket nao tem bucket policy: a resposta de
    ``GetBucketPolicy`` e o elemento ``Policy``, ``Required: No``, e a ausencia de
    policy e um estado legitimo -- o mesmo que a API sinaliza com ``NoSuchBucketPolicy``.

    ``public_access_block`` e sempre presente (os quatro membros sao ``Required: No`` e
    um bucket sem configuracao tem os quatro em ``False``).
    """

    resource_uuid: str
    bucket_name: str
    account_id: str
    region_id: str
    creation_date: str
    owner: AwsAclOwner
    acl_grants: tuple[AwsBucketGrant, ...]
    policy: AwsBucketPolicy | None
    public_access_block: AwsPublicAccessBlock
    #: O bloco por REGIAO, ou ``None`` quando a conta nao definiu um. Ver
    #: :class:`AwsRegionalAccessBlock` para por que ele nao e um quinto membro do bloco de
    #: bucket: as duas acoes publicadas nao documentam nenhum membro regional.
    regional_access_block: AwsRegionalAccessBlock | None = None

    def effective_grants(self) -> tuple[AwsBucketGrant, ...]:
        """The ACL ``GetBucketAcl`` publishes: the enforced one, not the stored one.

        With ``IgnorePublicAcls`` on, the documented behaviour is that the call returns
        the permissions S3 is ENFORCING, so the grants to the two predefined public
        groups are not part of the answer. Any other grant survives, because the setting
        "doesn't affect the persistence of any existing ACLs" -- it changes what the
        call reports, not what is stored.
        """
        if not self.public_access_block.ignore_public_acls:
            return self.acl_grants
        public = frozenset(S3_PUBLIC_GROUP_URIS)
        return tuple(grant for grant in self.acl_grants if grant.uri not in public)