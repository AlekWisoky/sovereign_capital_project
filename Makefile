.PHONY: local-bootstrap local-boot verify-backend verify-mobile

local-bootstrap:
	./scripts/bootstrap_local.sh

local-boot:
	./scripts/local_boot.sh

verify-backend:
	./scripts/verify_boot.sh

verify-mobile:
	./scripts/verify_mobile.sh
