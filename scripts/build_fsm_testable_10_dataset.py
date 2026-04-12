from __future__ import annotations

import json
from pathlib import Path


PROJECT_TEMPLATE_DIR = "benchmarks/foundry_oz"
SOURCE_RELPATH = "src/Generated.sol"
TEST_RELPATH = "test/Generated.t.sol"
MAIN_SAMPLE_IDS = {0, 2, 5, 8, 9}
DIAGNOSTIC_SAMPLE_IDS = {1, 3, 4, 6, 7}


def sample(
    *,
    sample_id: int,
    source_fsm_id: str,
    source_contract_name: str,
    contract_name: str,
    category: str,
    instruction: str,
    test_code: str,
    required_abi_signatures: list[str],
    forbidden_abi_signatures: list[str] | None = None,
) -> dict:
    return {
        "id": sample_id,
        "source_fsm_id": source_fsm_id,
        "source_contract_name": source_contract_name,
        "dataset_source": "fsm_scg_curated_testable",
        "contract_name": contract_name,
        "category": category,
        "difficulty": "easy",
        "instruction": instruction.strip(),
        "language": "solidity",
        "version": "0.8.20",
        "evm_version": "shanghai",
        "source_relpath": SOURCE_RELPATH,
        "project_template_dir": PROJECT_TEMPLATE_DIR,
        "test_relpath": TEST_RELPATH,
        "include_paths": ["lib"],
        "test_code": test_code.strip() + "\n",
        "required_abi_signatures": required_abi_signatures,
        "forbidden_abi_signatures": forbidden_abi_signatures or [],
    }


SAMPLES = [
    sample(
        sample_id=0,
        source_fsm_id="8",
        source_contract_name="MembershipContract",
        contract_name="MembershipAirdrop",
        category="membership_airdrop",
        instruction="""
Write a complete Solidity smart contract named MembershipAirdrop using Solidity 0.8.20.
This task is curated from an FSM-SCG membership/airdrop sample. Do not use external imports.
Preserve the exact public interface specified below; do not narrow uint256 arguments to smaller integer types for gas optimization.
The contract must:
1. store an owner set to the deployer;
2. expose setTier(address user, uint256 tier) as an only-owner function;
3. expose public mappings tierOf(address), claimed(address), airdropCredits(address), and purchasedTokens(address);
4. expose claimAirdrop() so a user with tier > 0 can claim exactly once, adding tier * 100 credits;
5. expose purchaseTokens() payable so a tiered user can purchase tokens, requiring msg.value > 0 and adding msg.value * 1000 / 1 ether tokens;
6. expose withdrawAll() as only-owner and transfer the full ETH balance to the owner;
7. revert for unauthorized owner-only calls, users without tier, duplicate airdrop claims, and zero-value purchases.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    MembershipAirdrop c;
    address user = address(0xBEEF);

    receive() external payable {}

    function setUp() public {
        c = new MembershipAirdrop();
        vm.deal(user, 2 ether);
    }

    function testOwnerCanSetTierAndUserClaimsOnce() public {
        uint256 tier = 2;
        c.setTier(user, tier);
        assertEq(c.tierOf(user), tier);
        vm.prank(user);
        c.claimAirdrop();
        assertEq(c.airdropCredits(user), 200);
        assertTrue(c.claimed(user));
        vm.prank(user);
        vm.expectRevert();
        c.claimAirdrop();
    }

    function testNonOwnerCannotSetTier() public {
        vm.prank(user);
        vm.expectRevert();
        c.setTier(user, 1);
    }

    function testUntieredUserCannotClaim() public {
        vm.prank(user);
        vm.expectRevert();
        c.claimAirdrop();
    }

    function testTieredUserCanPurchase() public {
        uint256 tier = 1;
        c.setTier(user, tier);
        vm.prank(user);
        c.purchaseTokens{value: 1 ether}();
        assertEq(c.purchasedTokens(user), 1000);
    }

    function testUntieredUserCannotPurchase() public {
        vm.prank(user);
        vm.expectRevert();
        c.purchaseTokens{value: 1 ether}();
    }

    function testZeroValuePurchaseReverts() public {
        uint256 tier = 1;
        c.setTier(user, tier);
        vm.prank(user);
        vm.expectRevert();
        c.purchaseTokens{value: 0}();
    }

    function testNonOwnerCannotWithdrawAll() public {
        vm.prank(user);
        vm.expectRevert();
        c.withdrawAll();
    }

    function testOwnerCanWithdrawAll() public {
        uint256 tier = 1;
        c.setTier(user, tier);
        vm.prank(user);
        c.purchaseTokens{value: 1 ether}();

        uint256 ownerBalanceBefore = address(this).balance;
        c.withdrawAll();
        assertEq(address(c).balance, 0);
        assertEq(address(this).balance, ownerBalanceBefore + 1 ether);
    }
}
""",
        required_abi_signatures=[
            "setTier(address,uint256)",
            "tierOf(address)",
            "claimed(address)",
            "airdropCredits(address)",
            "purchasedTokens(address)",
            "claimAirdrop()",
            "purchaseTokens()",
            "withdrawAll()",
        ],
    ),
    sample(
        sample_id=1,
        source_fsm_id="5632",
        source_contract_name="CrowdsaleContract",
        contract_name="SimpleCrowdsale",
        category="crowdsale",
        instruction="""
Write a complete Solidity smart contract named SimpleCrowdsale using Solidity 0.8.20.
This task is curated from an FSM-SCG crowdsale sample. Do not use external imports.
The contract must:
1. be constructed with address payable wallet and uint256 rate;
2. reject a zero wallet or zero rate in the constructor;
3. expose public wallet(), rate(), weiRaised(), and tokensPurchased(address) values;
4. expose buyTokens(address beneficiary) payable;
5. buyTokens must require a nonzero beneficiary and nonzero msg.value, add msg.value to weiRaised, add msg.value * rate to tokensPurchased[beneficiary], emit TokensPurchased(address purchaser, address beneficiary, uint256 value, uint256 amount), and forward the ETH to wallet.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    SimpleCrowdsale c;
    address payable wallet = payable(address(0xCAFE));
    address buyer = address(0xBEEF);

    function setUp() public {
        c = new SimpleCrowdsale(wallet, 5);
        vm.deal(buyer, 3 ether);
    }

    function testBuyTokensForwardsFundsAndRecordsPurchase() public {
        vm.prank(buyer);
        c.buyTokens{value: 2 ether}(buyer);
        assertEq(c.weiRaised(), 2 ether);
        assertEq(c.tokensPurchased(buyer), 10 ether);
        assertEq(wallet.balance, 2 ether);
    }

    function testRejectsZeroValue() public {
        vm.prank(buyer);
        vm.expectRevert();
        c.buyTokens{value: 0}(buyer);
    }

    function testRejectsZeroBeneficiary() public {
        vm.prank(buyer);
        vm.expectRevert();
        c.buyTokens{value: 1 ether}(address(0));
    }
}
""",
        required_abi_signatures=[
            "constructor(address,uint256)",
            "wallet()",
            "rate()",
            "weiRaised()",
            "tokensPurchased(address)",
            "buyTokens(address)",
        ],
    ),
    sample(
        sample_id=2,
        source_fsm_id="15",
        source_contract_name="TeamVestingContract",
        contract_name="TeamVestingVault",
        category="vesting",
        instruction="""
Write a complete Solidity smart contract named TeamVestingVault using Solidity 0.8.20.
This task is curated from an FSM-SCG team vesting sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. expose public mappings allocation(address), releaseTime(address), and withdrawn(address);
3. expose addInvestor(address investor, uint256 amount, uint256 unlockTime) as only-owner;
4. addInvestor must reject the zero address and amount == 0;
5. expose withdraw() so an investor can withdraw only after block.timestamp >= releaseTime[msg.sender], then set allocation[msg.sender] to 0 and add the withdrawn amount to withdrawn[msg.sender];
6. revert for unauthorized owner-only calls, early withdrawal, or withdrawal with no allocation.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    TeamVestingVault c;
    address investor = address(0xBEEF);

    function setUp() public {
        c = new TeamVestingVault();
    }

    function testOwnerAddsInvestor() public {
        c.addInvestor(investor, 100, block.timestamp + 1 days);
        assertEq(c.allocation(investor), 100);
    }

    function testNonOwnerCannotAddInvestor() public {
        vm.prank(investor);
        vm.expectRevert();
        c.addInvestor(investor, 100, block.timestamp + 1 days);
    }

    function testInvestorWithdrawsAfterUnlock() public {
        c.addInvestor(investor, 100, block.timestamp + 1 days);
        vm.prank(investor);
        vm.expectRevert();
        c.withdraw();
        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(investor);
        c.withdraw();
        assertEq(c.allocation(investor), 0);
        assertEq(c.withdrawn(investor), 100);
    }
}
""",
        required_abi_signatures=[
            "allocation(address)",
            "releaseTime(address)",
            "withdrawn(address)",
            "addInvestor(address,uint256,uint256)",
            "withdraw()",
        ],
    ),
    sample(
        sample_id=3,
        source_fsm_id="49",
        source_contract_name="TokenVotingContract",
        contract_name="TokenVoting",
        category="voting",
        instruction="""
Write a complete Solidity smart contract named TokenVoting using Solidity 0.8.20.
This task is curated from an FSM-SCG token/voting sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. define candidates by id and name, and expose candidateCount(), candidateNames(uint256), and candidateVotes(uint256);
3. expose addCandidate(string memory name) as only-owner;
4. expose grantVotingRights(address voter) as only-owner and a public hasVotingRights(address) mapping or getter;
5. expose vote(uint256 candidateId), allowing each granted voter to vote exactly once;
6. reject invalid candidate ids, duplicate votes, and votes from addresses without voting rights.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    TokenVoting c;
    address voter = address(0xBEEF);

    function setUp() public {
        c = new TokenVoting();
        c.addCandidate("Alice");
        c.addCandidate("Bob");
    }

    function testOwnerAddsCandidates() public {
        assertEq(c.candidateCount(), 2);
        assertEq(c.candidateNames(1), "Alice");
    }

    function testGrantedVoterCanVoteOnce() public {
        c.grantVotingRights(voter);
        vm.prank(voter);
        c.vote(1);
        assertEq(c.candidateVotes(1), 1);
        vm.prank(voter);
        vm.expectRevert();
        c.vote(1);
    }

    function testUngrantVoterCannotVote() public {
        vm.prank(voter);
        vm.expectRevert();
        c.vote(1);
    }
}
""",
        required_abi_signatures=[
            "candidateCount()",
            "candidateNames(uint256)",
            "candidateVotes(uint256)",
            "addCandidate(string)",
            "grantVotingRights(address)",
            "hasVotingRights(address)",
            "vote(uint256)",
        ],
    ),
    sample(
        sample_id=4,
        source_fsm_id="53",
        source_contract_name="UncensorablePostingContract",
        contract_name="PostingBoard",
        category="posting",
        instruction="""
Write a complete Solidity smart contract named PostingBoard using Solidity 0.8.20.
This task is curated from an FSM-SCG uncensorable posting sample. Do not use external imports.
The contract must:
1. define a public postCount;
2. define a public posts(uint256) getter for a struct containing address author, string content, and uint256 totalPower;
3. expose createPost(string calldata content) returning the new post id and rejecting empty content;
4. expose boostPost(uint256 postId) payable, requiring an existing post and msg.value > 0, increasing that post's totalPower and adding the value to authorBalances(author);
5. expose authorBalances(address);
6. expose withdraw() so an author can withdraw their accumulated balance and the balance is set to zero before transferring ETH.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    PostingBoard c;
    address author = address(0xA11CE);
    address booster = address(0xBEEF);

    function setUp() public {
        c = new PostingBoard();
        vm.deal(booster, 2 ether);
    }

    function testCreatePostStoresAuthorAndContent() public {
        vm.prank(author);
        uint256 postId = c.createPost("hello");
        (address storedAuthor, string memory content, uint256 power) = c.posts(postId);
        assertEq(storedAuthor, author);
        assertEq(content, "hello");
        assertEq(power, 0);
    }

    function testBoostCreditsAuthor() public {
        vm.prank(author);
        uint256 postId = c.createPost("hello");
        vm.prank(booster);
        c.boostPost{value: 1 ether}(postId);
        assertEq(c.authorBalances(author), 1 ether);
    }

    function testInvalidBoostReverts() public {
        vm.prank(booster);
        vm.expectRevert();
        c.boostPost{value: 1 ether}(999);
    }
}
""",
        required_abi_signatures=[
            "postCount()",
            "posts(uint256)",
            "createPost(string)",
            "boostPost(uint256)",
            "authorBalances(address)",
            "withdraw()",
        ],
    ),
    sample(
        sample_id=5,
        source_fsm_id="2929",
        source_contract_name="TokenNFTCollectibles",
        contract_name="CollectibleSale",
        category="nft_sale",
        instruction="""
Write a complete Solidity smart contract named CollectibleSale using Solidity 0.8.20.
This task is curated from an FSM-SCG NFT collectible sale sample. Do not use external imports.
The contract must:
1. store owner, maxSupply, price, totalMinted, saleEnded, and balances(address);
2. be constructed with uint256 maxSupply_ and uint256 price_;
3. expose buy(uint256 amount) payable, requiring sale is active, amount > 0, amount <= 10, totalMinted + amount <= maxSupply, and exact payment amount * price;
4. buy must increase balances[msg.sender] and totalMinted, and set saleEnded true when maxSupply is reached;
5. expose setPrice(uint256 newPrice) as only-owner;
6. expose withdraw() as only-owner and transfer the full ETH balance to the owner.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    CollectibleSale c;
    address buyer = address(0xBEEF);

    function setUp() public {
        c = new CollectibleSale(5, 0.1 ether);
        vm.deal(buyer, 1 ether);
    }

    function testBuyMintsCollectibles() public {
        vm.prank(buyer);
        c.buy{value: 0.2 ether}(2);
        assertEq(c.balances(buyer), 2);
        assertEq(c.totalMinted(), 2);
    }

    function testBuyRejectsWrongPayment() public {
        vm.prank(buyer);
        vm.expectRevert();
        c.buy{value: 0.1 ether}(2);
    }

    function testSaleEndsAtMaxSupply() public {
        vm.prank(buyer);
        c.buy{value: 0.5 ether}(5);
        assertTrue(c.saleEnded());
        vm.prank(buyer);
        vm.expectRevert();
        c.buy{value: 0.1 ether}(1);
    }
}
""",
        required_abi_signatures=[
            "constructor(uint256,uint256)",
            "maxSupply()",
            "price()",
            "totalMinted()",
            "saleEnded()",
            "balances(address)",
            "buy(uint256)",
            "setPrice(uint256)",
            "withdraw()",
        ],
    ),
    sample(
        sample_id=6,
        source_fsm_id="48",
        source_contract_name="FundManagementContract",
        contract_name="FundPoolManager",
        category="fund_management",
        instruction="""
Write a complete Solidity smart contract named FundPoolManager using Solidity 0.8.20.
This task is curated from an FSM-SCG fund management sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. expose pools(address pool) returning the reward token address for that pool;
3. expose addPool(address pool, address rewardToken) and removePool(address pool) as only-owner functions;
4. expose transferTo(address payable to, uint256 amount), callable only by a registered pool, transferring ETH from the contract to to;
5. expose rescueFund(address payable to, uint256 amount) as only-owner;
6. include receive() external payable;
7. reject zero pool addresses, unregistered pool transfers, and insufficient ETH balance transfers.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    FundPoolManager c;
    address pool = address(0xBEEF);
    address reward = address(0xCAFE);
    address payable receiver = payable(address(0xD00D));

    function setUp() public {
        c = new FundPoolManager();
        payable(address(c)).transfer(2 ether);
    }

    receive() external payable {}

    function testOwnerAddsAndRemovesPool() public {
        c.addPool(pool, reward);
        assertEq(c.pools(pool), reward);
        c.removePool(pool);
        assertEq(c.pools(pool), address(0));
    }

    function testRegisteredPoolTransfersFunds() public {
        c.addPool(pool, reward);
        vm.prank(pool);
        c.transferTo(receiver, 1 ether);
        assertEq(receiver.balance, 1 ether);
    }

    function testUnregisteredPoolCannotTransfer() public {
        vm.prank(pool);
        vm.expectRevert();
        c.transferTo(receiver, 1 ether);
    }
}
""",
        required_abi_signatures=[
            "pools(address)",
            "addPool(address,address)",
            "removePool(address)",
            "transferTo(address,uint256)",
            "rescueFund(address,uint256)",
            "receive()",
        ],
    ),
    sample(
        sample_id=7,
        source_fsm_id="2006",
        source_contract_name="NFTTokenContract",
        contract_name="PresaleMint",
        category="minting",
        instruction="""
Write a complete Solidity smart contract named PresaleMint using Solidity 0.8.20.
This task is curated from an FSM-SCG presale/public sale minting sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. define enum State { PresaleLive, SaleLive, SaleClosed } and public currentState initialized to PresaleLive;
3. expose whitelist(address user, bool status) as only-owner and public presalerList(address);
4. expose toggleSale() as only-owner, moving PresaleLive -> SaleLive and SaleLive -> SaleClosed;
5. expose presaleBuy() payable, requiring PresaleLive and presalerList[msg.sender] true, incrementing presaleAmountMinted;
6. expose buy() payable, requiring SaleLive and incrementing publicAmountMinted;
7. reject non-owner whitelist/toggle calls and invalid state purchases.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    PresaleMint c;
    address user = address(0xBEEF);

    function setUp() public {
        c = new PresaleMint();
        vm.deal(user, 1 ether);
    }

    function testWhitelistedUserCanPresaleBuy() public {
        c.whitelist(user, true);
        vm.prank(user);
        c.presaleBuy{value: 0.1 ether}();
        assertEq(c.presaleAmountMinted(), 1);
    }

    function testUnwhitelistedUserCannotPresaleBuy() public {
        vm.prank(user);
        vm.expectRevert();
        c.presaleBuy{value: 0.1 ether}();
    }

    function testPublicBuyOnlyWhenSaleLive() public {
        c.toggleSale();
        vm.prank(user);
        c.buy{value: 0.1 ether}();
        assertEq(c.publicAmountMinted(), 1);
    }
}
""",
        required_abi_signatures=[
            "currentState()",
            "presalerList(address)",
            "whitelist(address,bool)",
            "toggleSale()",
            "presaleBuy()",
            "buy()",
            "presaleAmountMinted()",
            "publicAmountMinted()",
        ],
    ),
    sample(
        sample_id=8,
        source_fsm_id="4381",
        source_contract_name="GrandGooseMansion",
        contract_name="GrandGooseMansion",
        category="nft_minting",
        instruction="""
Write a complete Solidity smart contract named GrandGooseMansion using Solidity 0.8.20.
This task is curated from an FSM-SCG NFT presale/public sale sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. expose public supply, cost, maxSupply, preSaleWalletLimit, and enum SaleStatus { Paused, Presale, PublicSale } with public currentSaleStatus initially Paused;
3. expose whitelistUser(address user, bool status), startPresale(), startPublicSale(), and setCost(uint256 newCost) as only-owner functions;
4. expose isWhitelisted(address user) view returns (bool);
5. expose mintTokenWhitelisted(uint256 amount) payable, requiring Presale, whitelist status, amount > 0, per-wallet presale limit, supply cap, and exact payment;
6. expose mintTokenPublic(uint256 amount) payable, requiring PublicSale, amount > 0, supply cap, and exact payment;
7. update supply and preSaleWalletMinted(address) on successful mint.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    GrandGooseMansion c;
    address user = address(0xBEEF);

    function setUp() public {
        c = new GrandGooseMansion();
        c.setCost(0.1 ether);
        vm.deal(user, 1 ether);
    }

    function testWhitelistedPresaleMint() public {
        c.whitelistUser(user, true);
        c.startPresale();
        vm.prank(user);
        c.mintTokenWhitelisted{value: 0.2 ether}(2);
        assertEq(c.supply(), 2);
        assertEq(c.preSaleWalletMinted(user), 2);
    }

    function testNonWhitelistedPresaleMintReverts() public {
        c.startPresale();
        vm.prank(user);
        vm.expectRevert();
        c.mintTokenWhitelisted{value: 0.1 ether}(1);
    }

    function testPublicMint() public {
        c.startPublicSale();
        vm.prank(user);
        c.mintTokenPublic{value: 0.1 ether}(1);
        assertEq(c.supply(), 1);
    }
}
""",
        required_abi_signatures=[
            "supply()",
            "cost()",
            "maxSupply()",
            "preSaleWalletLimit()",
            "currentSaleStatus()",
            "whitelistUser(address,bool)",
            "startPresale()",
            "startPublicSale()",
            "setCost(uint256)",
            "isWhitelisted(address)",
            "mintTokenWhitelisted(uint256)",
            "mintTokenPublic(uint256)",
            "preSaleWalletMinted(address)",
        ],
    ),
    sample(
        sample_id=9,
        source_fsm_id="3088",
        source_contract_name="NFTMintingContract",
        contract_name="ClosedPresaleMint",
        category="minting",
        instruction="""
Write a complete Solidity smart contract named ClosedPresaleMint using Solidity 0.8.20.
This task is curated from an FSM-SCG closed/presale/public minting sample. Do not use external imports.
The contract must:
1. store an owner set to the deployer;
2. define enum State { CLOSED, PRESALE, PUBLIC } and public currentState initially CLOSED;
3. be constructed with uint256 price_ and uint256 maxSupply_;
4. expose startPresale() and startPublicSale() as only-owner functions;
5. expose public price, totalSupply, maxSupply, and claimedWhitelistStatus(address);
6. expose mintNFT() payable, requiring PRESALE state, exact payment, caller not previously claimed, and available supply; it must mark claimedWhitelistStatus[msg.sender] true and increment totalSupply by 1;
7. expose mintPublicNFT(uint256 amount) payable, requiring PUBLIC state, amount > 0, exact payment, and available supply; it must increment totalSupply by amount.
Return only the Solidity code in a single ```solidity``` block.
""",
        test_code="""
// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "../src/Generated.sol";

contract GeneratedTest is Test {
    ClosedPresaleMint c;
    address user = address(0xBEEF);

    function setUp() public {
        c = new ClosedPresaleMint(0.1 ether, 3);
        vm.deal(user, 1 ether);
    }

    function testCannotMintWhileClosed() public {
        vm.prank(user);
        vm.expectRevert();
        c.mintNFT{value: 0.1 ether}();
    }

    function testPresaleMintOnce() public {
        c.startPresale();
        vm.prank(user);
        c.mintNFT{value: 0.1 ether}();
        assertEq(c.totalSupply(), 1);
        assertTrue(c.claimedWhitelistStatus(user));
        vm.prank(user);
        vm.expectRevert();
        c.mintNFT{value: 0.1 ether}();
    }

    function testPublicMint() public {
        c.startPublicSale();
        vm.prank(user);
        c.mintPublicNFT{value: 0.2 ether}(2);
        assertEq(c.totalSupply(), 2);
    }
}
""",
        required_abi_signatures=[
            "constructor(uint256,uint256)",
            "currentState()",
            "startPresale()",
            "startPublicSale()",
            "price()",
            "totalSupply()",
            "maxSupply()",
            "claimedWhitelistStatus(address)",
            "mintNFT()",
            "mintPublicNFT(uint256)",
        ],
    ),
]


def with_partition_tags(samples: list[dict]) -> list[dict]:
    tagged = []
    for entry in samples:
        item = dict(entry)
        if item["id"] in MAIN_SAMPLE_IDS:
            item["benchmark_partition"] = "main"
        elif item["id"] in DIAGNOSTIC_SAMPLE_IDS:
            item["benchmark_partition"] = "diagnostic"
        else:
            item["benchmark_partition"] = "unassigned"
        tagged.append(item)
    return tagged


def main() -> None:
    tagged_samples = with_partition_tags(SAMPLES)
    main_samples = [sample for sample in tagged_samples if sample["benchmark_partition"] == "main"]
    diagnostic_samples = [sample for sample in tagged_samples if sample["benchmark_partition"] == "diagnostic"]

    outputs = {
        Path("data/solidity_fsm_testable_10.json"): tagged_samples,
        Path("data/solidity_fsm_testable_main_5.json"): main_samples,
        Path("data/solidity_fsm_testable_diagnostic_5.json"): diagnostic_samples,
    }

    for output_path, samples in outputs.items():
        output_path.write_text(json.dumps(samples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(samples)} samples to {output_path}")


if __name__ == "__main__":
    main()
