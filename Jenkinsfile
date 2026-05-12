pipeline {
    agent any

    parameters {
        password(
            name: 'MISTRAL_KEY',
            defaultValue: '',
            description: 'Entrez votre clé API Mistral (ex: sk-...) [Uniquement pour les branches de développement/feature]'
        )
    }

    options {
        timeout(time: 20, unit: 'MINUTES')
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        BOTPRESS_URL = 'https://cdn.botpress.cloud'
    }

    stages {

        stage('1. Préparation de l\'Environnement') {
            steps {
                script {
                    // Détection et standardisation du nom de la branche
                    def rawBranch = env.BRANCH_NAME ?: env.GIT_BRANCH ?: "main"
                    def cleanBranch = rawBranch.split('/')[-1]
                    env.BRANCH_SLUG = cleanBranch.replaceAll('[^a-zA-Z0-9]', '-').toLowerCase()

                    echo "Branche détectée : ${env.BRANCH_SLUG}"

                    if (env.BRANCH_SLUG == 'main' || env.BRANCH_SLUG == 'master') {
                        // Configuration de Production (Branche main)
                        env.IS_MAIN = 'true'
                        env.QDRANT_PORT = '6334'
                        env.N8N_PORT = '5679'
                        env.QDRANT_CONTAINER = 'ia_qdrant'
                        env.N8N_CONTAINER = 'ia_n8n'
                        env.QDRANT_URL = 'http://qdrant:6333'
                        env.N8N_URL = 'http://n8n:5678'
                        env.VENV = "/var/jenkins_home/venv/projet_ia"
                    } else {
                        // Configuration d'Isolation (Branches Feature)
                        env.IS_MAIN = 'false'
                        env.QDRANT_PORT = "${10000 + env.BUILD_NUMBER.toInteger()}"
                        env.N8N_PORT = "${20000 + env.BUILD_NUMBER.toInteger()}"
                        env.QDRANT_CONTAINER = "qdrant-${env.BRANCH_SLUG}"
                        env.N8N_CONTAINER = "n8n-${env.BRANCH_SLUG}"
                        env.QDRANT_URL = "http://qdrant-${env.BRANCH_SLUG}:6333"
                        env.N8N_URL = "http://n8n-${env.BRANCH_SLUG}:5678"
                        env.VENV = "/var/jenkins_home/venv/projet_ia_${env.BRANCH_SLUG}"

                        // Validation de la clé Mistral en mode interactif
                        if (!params.MISTRAL_KEY) {
                            error "❌ Clé Mistral non fournie. Relancez le build avec paramètres et entrez votre clé API."
                        }
                        env.MISTRAL_KEY_VALUE = params.MISTRAL_KEY
                    }

                    env.PYTHON = "${env.VENV}/bin/python"
                    env.PIP    = "${env.VENV}/bin/pip"

                    checkout scm
                }
            }
        }

        stage('2. Contrôle Qualité') {
            steps {
                sh '''
                echo "=== Python ==="
                find . -name "*.py" ! -path "*/venv/*" ! -path "*/.git/*" -exec python3 -m py_compile {} + && echo "Python : OK"

                echo "=== JSON ==="
                find . -name "*.json" ! -path "*/venv/*" ! -path "*/.git/*" -exec python3 -m json.tool {} + > /dev/null && echo "JSON : OK"

                echo "=== YAML ==="
                find . \\( -name "*.yml" -o -name "*.yaml" \\) ! -path "*/venv/*" ! -path "*/.git/*" -exec python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" {} \\; && echo "YAML : OK"

                echo "=== HTML ==="
                find . -name "*.html" ! -path "*/venv/*" ! -path "*/.git/*" | while read f; do
                    python3 -c "
import sys
from html.parser import HTMLParser

class Check(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.void = ['br','hr','img','input','meta','link','base','col','embed','param','source','track','wbr']
    def handle_starttag(self, tag, attrs):
        if tag not in self.void:
            self.stack.append(tag)
    def handle_endtag(self, tag):
        if tag in self.void:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            print('ERREUR: balise mal fermee </' + tag + '> dans $f')
            sys.exit(1)

p = Check()
p.feed(open('$f').read())
if p.stack:
    print('ERREUR: balises non fermees', p.stack, 'dans $f')
    sys.exit(1)
print('OK:', '$f')
" || exit 1
                done
                echo "HTML : OK"

                echo "=== Fichiers Data ==="
                [ -s "Wathiqa.bpz" ] && echo "Wathiqa.bpz : OK" || echo "Wathiqa.bpz : ATTENTION"
                [ -d "documents" ] && find documents -type f -not -empty | wc -l | xargs echo "Documents prets :" || echo "Alerte : pas de documents !"
                '''
            }
        }

        stage('3. Déploiement des Services') {
            steps {
                script {
                    sh '''
                    # Installation Docker si absent
                    command -v docker || apt-get install -y docker.io

                    # Réseau commun ia_network
                    docker network create ia_network 2>/dev/null || true
                    docker network connect ia_network fstm_jenkins 2>/dev/null || true
                    '''

                    if (env.IS_MAIN == 'true') {
                        // En production (main), on déploie ou démarre sans tout casser
                        sh '''
                        # Nettoyage automatique des anciens conteneurs pour appliquer les nouveaux ports
                        docker rm -f ia_qdrant || true
                        docker rm -f ia_n8n || true

                        # ── Qdrant Production ──
                        if ! docker ps -a --format "{{.Names}}" | grep -q "^ia_qdrant$"; then
                            echo "Déploiement initial de Qdrant..."
                            docker run -d \
                                --name ia_qdrant \
                                --network ia_network \
                                --network-alias qdrant \
                                -p 6334:6333 \
                                --restart unless-stopped \
                                qdrant/qdrant:latest
                        elif ! docker ps --format "{{.Names}}" | grep -q "^ia_qdrant$"; then
                            echo "Démarrage de ia_qdrant arrêté..."
                            docker start ia_qdrant
                        else
                            echo "ia_qdrant est déjà en cours d'exécution."
                        fi

                        # ── n8n Production ──
                        if ! docker ps -a --format "{{.Names}}" | grep -q "^ia_n8n$"; then
                            echo "Déploiement initial de n8n..."
                            docker run -d \
                                --name ia_n8n \
                                --network ia_network \
                                --network-alias n8n \
                                -p 5679:5678 \
                                --restart unless-stopped \
                                n8nio/n8n:latest
                        elif ! docker ps --format "{{.Names}}" | grep -q "^ia_n8n$"; then
                            echo "Démarrage de ia_n8n arrêté..."
                            docker start ia_n8n
                        else
                            echo "ia_n8n est déjà en cours d'exécution."
                        fi
                        '''
                    } else {
                        // En développement, nettoyage systématique pour un déploiement éphémère à neuf
                        sh '''
                        docker stop qdrant-${BRANCH_SLUG} n8n-${BRANCH_SLUG} || true
                        docker rm   qdrant-${BRANCH_SLUG} n8n-${BRANCH_SLUG} || true

                        docker run -d --name qdrant-${BRANCH_SLUG} --network ia_network --network-alias qdrant-${BRANCH_SLUG} -p ${QDRANT_PORT}:6333 qdrant/qdrant:latest
                        docker run -d --name n8n-${BRANCH_SLUG}    --network ia_network --network-alias n8n-${BRANCH_SLUG}    -p ${N8N_PORT}:5678    n8nio/n8n:latest
                        '''
                    }
                    sh 'sleep 5'
                }
            }
        }

        stage('4. Vérification de Santé') {
            parallel {

                stage('Qdrant Health') {
                    steps {
                        script {
                            def qdrantOK = false
                            for (int i = 1; i <= 3; i++) {
                                qdrantOK = (sh(script: "curl -sf --max-time 10 ${env.QDRANT_URL}", returnStatus: true) == 0)
                                if (qdrantOK) break
                                echo "Qdrant non prêt (tentative ${i}/3) — essai de réveil..."
                                sh "docker restart ${env.QDRANT_CONTAINER} || true"
                                sleep 10
                            }
                            if (!qdrantOK) error "Qdrant injoignable sur ${env.QDRANT_URL}"
                            echo "Qdrant : OK"
                        }
                    }
                }

                stage('n8n Health') {
                    steps {
                        script {
                            def n8nOK = false
                            for (int i = 1; i <= 6; i++) {
                                n8nOK = (sh(script: "curl -sf --max-time 5 ${env.N8N_URL}/healthz || curl -sf --max-time 5 ${env.N8N_URL}", returnStatus: true) == 0)
                                if (n8nOK) break
                                echo "n8n non prêt (tentative ${i}/6) — attente de 10s..."
                                sleep 10
                            }
                            if (!n8nOK) {
                                echo "n8n semble bloqué, tentative de redémarrage..."
                                sh "docker restart ${env.N8N_CONTAINER} || true"
                                sleep 20
                                n8nOK = (sh(script: "curl -sf --max-time 10 ${env.N8N_URL}", returnStatus: true) == 0)
                            }
                            if (!n8nOK) error "n8n injoignable sur ${env.N8N_URL}"
                            echo "n8n : OK"
                        }
                    }
                }

                stage('Botpress Cloud') {
                    steps {
                        script {
                            def botpressOK = false
                            for (int i = 1; i <= 3; i++) {
                                botpressOK = (sh(script: "curl -sf --max-time 10 ${env.BOTPRESS_URL}", returnStatus: true) == 0)
                                if (botpressOK) break
                                sleep 5
                            }
                            echo "Botpress : ${botpressOK ? 'OK' : 'AVERTISSEMENT (non bloquant)'}"
                        }
                    }
                }
            }
        }

        stage('5. Installation') {
            steps {
                sh '''
                [ ! -d "$VENV" ] && python3 -m venv "$VENV"

                # Vérifie si tous les packages sont déjà installés
                echo "Vérification des packages..."
                MISSING=$("$PIP" install --dry-run -r requirements.txt 2>&1 | grep "Would install" || echo "")

                if [ -z "$MISSING" ]; then
                    echo "Tous les packages déjà installés — rien à faire."
                else
                    echo "Packages manquants : $MISSING"
                    "$PIP" install --upgrade pip -q
                    "$PIP" install -r requirements.txt -q --cache-dir "/var/jenkins_home/.pip_cache"
                    echo "Installation terminée avec succès."
                fi
                '''
            }
        }

        stage('6. Indexation IA & RAG') {
            options { timeout(time: 15, unit: 'MINUTES') }
            steps {
                script {
                    if (env.IS_MAIN == 'true') {
                        withCredentials([string(credentialsId: 'MISTRAL_KEY', variable: 'MISTRAL_KEY')]) {
                            env.MISTRAL_KEY_VALUE = env.MISTRAL_KEY
                        }
                    }
                }
                sh """
                export MISTRAL_KEY=${env.MISTRAL_KEY_VALUE}
                export QDRANT_URL=${env.QDRANT_URL}
                "\$PYTHON" load.py
                """
                sh '''
                COLLECTIONS=$(curl -sf "${QDRANT_URL}/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
cols = data.get('result', {}).get('collections', [])
print(len(cols))
")
                [ "$COLLECTIONS" -gt 0 ] && echo "$COLLECTIONS collection(s) indexee(s)." || { echo "Aucune collection trouvee."; exit 1; }
                '''
            }
        }
    }

    post {
        success {
            echo "Succès sur la branche ${env.BRANCH_SLUG} !"
            script {
                if (env.IS_MAIN == 'false') {
                    echo "Succès détecté sur branche feature : Nettoyage des conteneurs éphémères..."
                    sh "docker stop qdrant-${env.BRANCH_SLUG} n8n-${env.BRANCH_SLUG} || true"
                    sh "docker rm   qdrant-${env.BRANCH_SLUG} n8n-${env.BRANCH_SLUG} || true"
                }
            }
        }
        failure {
            script {
                if (env.IS_MAIN == 'false') {
                    echo "Échec détecté sur branche feature : Nettoyage des conteneurs éphémères..."
                    sh "docker stop qdrant-${env.BRANCH_SLUG} n8n-${env.BRANCH_SLUG} || true"
                    sh "docker rm   qdrant-${env.BRANCH_SLUG} n8n-${env.BRANCH_SLUG} || true"
                } else {
                    echo "Échec détecté sur main — Conteneurs permanents préservés."
                }
            }
        }
        cleanup {
            cleanWs(deleteDirs: true, notFailBuild: true)
        }
    }
}
