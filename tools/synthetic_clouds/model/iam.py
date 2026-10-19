"""Os fatos de IDENTIDADE de uma conta AWS -- a chave que as tres regras de IAM leem.

As tres regras de identidade do catalogo do AWS Config -- ``root-account-mfa-enabled``,
``iam-password-policy`` e ``access-keys-rotated`` -- respondiam ``INSUFFICIENT_DATA`` por
lacuna de MODELO nomeada: o estate nao carregava nenhum fato de IAM. E o Incremento 4
pela mesma razao que o Incremento 2 fez pelos grupos e o Incremento 3 pelos buckets: o
recurso ja era inventariado e faturado, mas nada no estate carregava o CONTEUDO que a
regra leria.

Fica numa colecao propria (``CanonicalEstate.aws_identity_postures``) e nao como coluna em
``Resource`` pelos mesmos motivos de :class:`AwsBucketPosture`: ``Resource`` e o portador de
identidade FOCUS 1.2 e cada consumidor de faturamento le a coluna a coluna; um
``mfa_active`` dentro dele colocaria um campo que nenhuma coluna FOCUS define dentro do
registro que define todas elas.

Duas diferencas estruturais em relacao aos incrementos anteriores, que valem registrar:

1. **A chave e a CONTA, nao um recurso.** Os grupos e os buckets sao por recurso
   (``resource_uuid``); IAM e global -- a senha da conta, o MFA do root e as chaves dos
   usuarios nao tem regiao. A FK e portanto ``AwsAccount.account_id``, de
   ``model/hierarchy.py``, e nao ``Resource.identity.uuid``.
2. **A regra responde por conta e se repete em cada escopo regional.** A superficie do
   Config Configura regra por (conta, regiao), mas o fato de IAM e por conta: as N regioes
   de uma conta veem o MESMO veredito. E por isso que o veredito se repete em vez de
   diferir -- um veredito diferente por regiao seria um fato inventado.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class AwsRootAccountMfa:
    """O estado de MFA da conta ROOT -- o que ``root-account-mfa-enabled`` le.

    ``mfa_active`` e o booleano da propria regra. ``root_access_keys`` quantifica as
    credenciais de longa vida da conta root, porque e o outro lado do mesmo risco e a
    ``iam-password-policy`` nao a avalia -- ela existe para o renderer ``s3_posture``
    deixar de ser a unica fonte de "exposto".

    A conta root e a unica identidade que AWS proibe de gerenciar: nao tem usuario, nao tem
    policy, nao tem MFA gerenciavel -- o fuso e binario por construcao. E por isso que este
    registro nao tem ``arn``, ``path`` nem ``user_name``: sao atributos de usuario IAM, e a
    raiz nao e um usuario.

    ``user_creation_time`` e ``root_access_key_last_rotated`` sao os dois fatos que o
    credential report publica para a linha da raiz alem do MFA. O ultimo e ``None`` quando a
    conta nao tem chave de longa vida, e o report escreve ``N/A`` nesse caso -- nao uma data.
    """

    mfa_active: bool
    root_access_keys: int  # 0 = nenhuma, 2 = o par que a AWS cria na conta
    user_creation_time: str  # ISO-8601; a conta root nasce com a conta
    root_access_key_last_rotated: str | None  # None = sem chave de longa vida


@dataclass(slots=True, frozen=True)
class AwsPasswordPolicy:
    """A senha da CONTA -- o que ``iam-password-policy`` le.

    Cada membro e o valor publicado por ``iam:GetAccountPasswordPolicy``. Os quatro
    ``require_*`` sao booleanos porque a API os publica assim, mas a regra gerenciada os
    compara com um parametro inteiro: ``-1`` significa "nao exigir" e qualquer valor
    positivo significa "exigir". O metodo :meth:`exige` e quem faz essa traducao, para que
    nem o renderer nem o teste de fidelidade repitam a regra por conta propria.

    ``hard_expiry`` e ``max_password_age_days`` nao sao o mesmo interruptor: ``hard_expiry``
    responde se o usuario pode trocar a propria senha expirada pelo console, e
    ``max_password_age_days`` responde quantos dias a senha vive.
    ``password_reuse_prevention`` e independente dos dois.
    """

    minimum_password_length: int
    require_symbols: bool
    require_numbers: bool
    require_uppercase: bool
    require_lowercase: bool
    allow_users_to_change_password: bool
    hard_expiry: bool
    max_password_age_days: int | None
    password_reuse_prevention: int | None

    @property
    def expire_passwords(self) -> bool:
        """``ExpirePasswords`` DERIVADO de ``MaxPasswordAge``, como a pagina do tipo define.

        A pagina de ``PasswordPolicy`` nao descreve este membro como um interruptor que se
        liga: ela diz que ele "Returns true if MaxPasswordAge contains a value greater than 0.
        Returns false if MaxPasswordAge is 0 or not present."

        Por isso ele e uma propriedade e nao um campo. Com dois campos, o modelo aceitaria o
        estado que a AWS nunca devolve -- ``ExpirePasswords`` verdadeiro com ``MaxPasswordAge``
        ausente -- e o renderer teria de escolher entre publicar um membro contraditorio e
        publicar um valor que nao veio do estado.
        """
        return bool(self.max_password_age_days and self.max_password_age_days > 0)

    def exige(self, *, parametro: int) -> bool | None:
        """Se o parametro da regra exige este requisito; ``None`` se ele nao o avalia.

        A regra gerenciada documenta o parametro como inteiro e usa ``-1`` para nao
        avaliar. Traduzir aqui, e nao no renderer, e o que impede o teste de fidelidade de
        reimplementar a semantica que ele deveria estar conferindo.
        """
        if parametro < 0:
            return None
        return bool(parametro)


@dataclass(slots=True, frozen=True)
class AwsAccessKey:
    """Uma chave de acesso de um usuario IAM -- o que ``access-keys-rotated`` le.

    ``status`` e o vocabulario da propria API (``Active``/``Inactive``), e nao um booleano
    inventado. ``last_used_date`` e ``None`` quando a chave nunca foi usada, que e um estado
    legitimo e NAO a mesma coisa de uma chave recem-criada: a regra de rotacao le a idade de
    criacao, e uma chave nunca usada nao e mais antiga do que uma chave de ontem.
    """

    access_key_id: str
    status: str  # "Active" | "Inactive"
    create_date: str  # ISO-8601 (YYYY-MM-DD)
    last_used_date: str | None  # None = nunca usada


@dataclass(slots=True, frozen=True)
class AwsIamUser:
    """Um usuario IAM.

    ``password_enabled`` e o que separa "tem acesso ao console" de "so usa a API": um
    usuario so de servico nao tem senha e nao tem console que proteger com MFA. E o criterio
    que o consumidor de posture usa para nao acusar um usuario de API como se fosse um
    humano sem MFA.

    ``arn`` e o que o consumidor nomeia no achado; ele carrega o ``UserName`` porque e o
    prefixo e porque o ARN sozinho obriga o consumidor a decodificar o nome.

    Os tres campos de data sao os que o credential report publica: ``user_creation_time`` e
    quando o usuario nasceu, ``password_last_used`` e quando a senha abriu um site da AWS pela
    ultima vez, ``password_last_changed`` e quando a senha foi posta pela ultima vez. Os dois
    ultimos sao ``None`` para quem NAO tem senha -- e o report escreve ``N/A`` nesse caso, nao
    uma data: e um usuario so de API tem as tres colunas em ``N/A`` e nenhuma delas pode ser
    lida como "1970" ou "hoje".
    """

    user_name: str
    arn: str  # arn:aws:iam::<account-id>:user[/<path>]<name>
    path: str  # "/" ou "/servico/", etc.
    password_enabled: bool
    mfa_active: bool
    access_keys: tuple[AwsAccessKey, ...]
    user_creation_time: str  # ISO-8601
    password_last_used: str | None  # None = sem senha -> o report escreve "N/A"
    password_last_changed: str | None  # None = sem senha -> o report escreve "N/A"

    @property
    def console_user(self) -> bool:
        """Whether this user signs in to a console at all (it has a password).

        A regra de MFA so tem o que avaliar sobre um usuario com console: um usuario de
        servico sem senha nao tem tela para proteger. Por isso a propriedade existe e nao um
        campo -- e o filtro que o consumidor e a regra compartilham.
        """
        return self.password_enabled


@dataclass(slots=True, frozen=True)
class AwsIdentityPosture:
    """A postura de IDENTIDADE de UMA conta -- a chave que as tres regras de IAM leem.

    Uma instancia por conta do estate. ``users`` pode ser vazia: uma conta sem nenhum
    usuario IAM e um estado legitimo, e nesse caso ``access-keys-rotated`` responde
    ``COMPLIANT`` com zero contribuidores, porque nao existe chave para rotacionar -- e nao
    ``INSUFFICIENT_DATA``, que diria que o estate nao sabe, quando ele sabe.
    """

    account_id: str  # FK -> AwsAccount.account_id
    root_mfa: AwsRootAccountMfa
    password_policy: AwsPasswordPolicy
    users: tuple[AwsIamUser, ...]

    def user(self, user_name: str) -> AwsIamUser | None:
        """Return the user named ``user_name``, or ``None`` when the account has no such user."""
        return next((u for u in self.users if u.user_name == user_name), None)